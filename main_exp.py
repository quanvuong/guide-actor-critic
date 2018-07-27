# This python scipt implements the guide actor-critic method in the paper "Guide Actor-Critic for Continuous Control", ICLR 2018.
# The experiments are done in python 3.5.3 using Keras 2.1.4, tensorflow-gpu 1.2.1, gym 0.9.1, mujoco-py 0.5.7 (Mujoco 1.3.1), numpy 1.14.0, scipy 1.0.0
# To run experiment for half-cheetah task for example, execute: python main_exp.py --env 2 --seed 0
# Please see the env_dict variable for index to each gym environment.

import argparse
import os
import platform
import time
import numpy as np
import tensorflow as tf
import random as rn
from keras import backend as K
import gym
import mujoco_py
from collections import deque
os.environ['TF_CPP_MIN_LOG_LEVEL']='3'  #Do not show gpu information when running tensorflow

from GAC_learner import GAC_learner
from tqdm import trange

# A simple numpy array as reply buffer.
class Data_buffer_nparray():
    def __init__(self, max_size, array_dim):
        self.max_size = max_size
        self.cur_index = 0
        self.total_size = 0
        self.buffer = np.zeros((array_dim, max_size))

    def reset(self):
        self.cur_index = 0
        self.total_size = 0
        self.buffer = np.zeros(self.buffer.shape)

    def get_data(self, indexes):
        return self.buffer[:,indexes]

    def get_size(self):
        return self.total_size

    def append(self, data):
        self.buffer[:,self.cur_index] = data
        self.cur_index = self.cur_index + 1
        if self.cur_index >= self.max_size:
            self.cur_index = 0

        if self.total_size < self.max_size:
            self.total_size = self.total_size + 1
        return

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Run experiments.")
    parser.add_argument("-s", "--seed", dest="seed", default=0, type=int, help="Random seed")

    ## Environment and experiment options
    parser.add_argument("-e", "--env", dest="env_name", default="Pendulum-v0", type=str, help="Name of a gym environment. Default is Pendulum.")
    parser.add_argument("-tstep", "--time_step", dest="time_step", default=1000, type=int, help="Maximum time steps in one episode")
    parser.add_argument("-sm", "--step_max", dest="step_max", default=1000000, type=int, help="Maximum time steps for training in total")
    parser.add_argument("-gamma", "--gamma", dest="gamma", default=0.99, type=float, help="Discount factor")

    ## Networks options
    parser.add_argument("-tau", "--tau", dest="tau",            default=0.001, type=float, help="Tau for updating the target Q-network")
    parser.add_argument("-lq", "--lr_q", dest="lr_q",         default=0.001, type=float, help="Learning rate the Q-network")
    parser.add_argument("-lp", "--lr_p", dest="lr_policy",    default=0.0001, type=float, help="Learning rate for the policy network")
    parser.add_argument("-rq", "--reg_q", dest="reg_q",      default=0, type=float, help="Regularizer for the Q-network")
    parser.add_argument("-rp", "--reg_p", dest="reg_policy", default=0, type=float, help="Regularizer for the Q-network")
    parser.add_argument("-bs", "--batch_size", dest="batch_size", default=256, type=int, help="Minibatch size")

    ## GAC options
    parser.add_argument("-mc", "--mincov", dest="min_cov",  default=0.01, type=float, help="Minimum entropy of the policy's covariance")
    parser.add_argument("-eps", "--eps", dest="epsilon",        default=0.0001, type=float, help="KL upper-bound")
    parser.add_argument("-eg", "--entropy_gamma", dest="entropy_gamma", default=0.99, type=float, help="Entropy reductin factor")
    parser.add_argument("-er", "--erate", dest="erate",     default=5000, type=int, help="Entropy reduction frequency, i.e, number of steps between each reduction.")
    parser.add_argument("-nt", "--n_taylor", dest="n_taylor", default=1, type=int, help="Number of samples for Taylor approximation. 0=GAC-0, 1=GAC-1")

    ## Result option
    parser.add_argument("-log_level", "--log_level", dest="log_level", default=0, type=int, \
                help="Amount of info. on the results. Set to 0 if only the return values are needed.")
    parser.add_argument("-rd", "--render", dest="render", default=0, type=int, help="Render graphics flag")

    args = parser.parse_args()
    seed        = args.seed
    env_name    = args.env_name
    T_max       = args.time_step
    min_cov     = args.min_cov
    erate       = args.erate
    batch_size      = args.batch_size
    gamma           = args.gamma
    entropy_gamma   = args.entropy_gamma
    step_max = args.step_max

    tau         = args.tau
    lr_q        = args.lr_q
    lr_policy   = args.lr_policy
    reg_q       = args.reg_q
    reg_policy  = args.reg_policy

    epsilon     = args.epsilon
    n_taylor    = args.n_taylor
    log_level = args.log_level
    render = args.render

    save_result = True
    save_model = True
    #N_test = 1
    N_test = 10
    test_interval = 1000

    # Set random seeds
    np.random.seed(seed)
    rn.seed(seed)
    tf.set_random_seed(seed)
    sess = tf.Session()
    K.set_session(sess)

    # Set Gym environment
    env = gym.make(env_name)    # This environment is used to collect data for training
    env.seed(seed)
    env_test = gym.make(env_name)   # This environment is used for testing
    env_test.seed(seed)

    # Set the action bound variables
    s_space = env.observation_space
    a_space = env.action_space
    ds = np.shape(s_space)[0]
    da = np.shape(a_space)[0]
    a_space_high = a_space.high
    a_space_low = a_space.low
    print("Env: %s, seed: %d" % (env_name, seed))

    # Set experiment name
    expname = "GAC-%d_%s_eps%0.4f_lrq%0.4f_lrp%0.4f_rq%0.4f_rp%0.4f_s%d" \
                % (n_taylor, env_name, epsilon, lr_q, lr_policy, reg_q, reg_policy, seed)

    # Create directory for results and models.
    if save_result:
        reward_path = "./Result/"
        try:
            import pathlib
            pathlib.Path("./Result/" + env_name).mkdir(parents=True, exist_ok=True)
            reward_path = "./Result/" + env_name + "/"
            filename = reward_path + expname + ".txt"
            print("Result will be recoreded in %s" % (filename))
        except:
            save_result = 0
            print("A result directory does not exist and cannot be created. The results are not saved")

    if save_model:
        model_path = "./Model/"
        try:
            import pathlib
            pathlib.Path("./Model/" + env_name).mkdir(parents=True, exist_ok=True)
            model_path = "./Model/" + env_name + "/"
        except:
            save_model = 0
            print("A model directory does not exist and cannot be created. The policy models are not saved")

    # Construct the learning agent
    learner = GAC_learner( ds=ds, da=da, sess=sess, \
                epsilon=epsilon, entropy_gamma=entropy_gamma, n_taylor=n_taylor, min_cov=min_cov, \
                gamma=gamma, tau=tau, lr_q=lr_q, lr_policy=lr_policy, \
                reg_q=reg_q, reg_policy=reg_policy, action_bnds =[a_space_low[0], a_space_high[0]], log_level=log_level)

    ## Reset the random seed
    np.random.seed(seed)

    ## Allocate replay buffers for each variable. Can be combined into one buffer with some indexing.
    max_buffer_size = 1000000
    state_buffer = Data_buffer_nparray(max_buffer_size, ds)
    action_buffer = Data_buffer_nparray(max_buffer_size, da)
    nextstate_buffer = Data_buffer_nparray(max_buffer_size, ds)
    reward_buffer = Data_buffer_nparray(max_buffer_size, 1)
    done_buffer = Data_buffer_nparray(max_buffer_size, 1)
    min_batch_size = T_max  # minimum size of the replay buffer before start training

    ## Initilize some logging variables
    loss_q_n, loss_pol_n = 0, 0
    eta_n, omega_n, beta_n = 0, 0, 0
    elapsed = 0

    ## For counting number of test iteration
    test_iter = 0

    ## For counting time step within an episode
    t = 0

    ## An array for recording expected return
    ret_te = np.zeros((np.ceil(step_max/test_interval).astype('int') + 1, N_test))

    ## start training loop
    state = env.reset()
    buffer_size = state_buffer.get_size()

    running_scores = []
    rew_buf = deque(maxlen=100)
    eps_rew = 0.0

    for i in trange(step_max):

        ## Draw an action from the current policy
        action = learner.draw_action(state)

        ## Take a step (Input actions are clipped to prevent runtime error of some gym environment)
        next_state, reward, done, _ = env.step(np.clip(action, a_min=a_space_low, a_max=a_space_high))

        eps_rew += reward

        t = t + 1
        if t == T_max:
            done = 1

        ## Add the transition to the replay buffers and move to next the state
        state_buffer.append(state)
        action_buffer.append(action)
        nextstate_buffer.append(next_state)
        reward_buffer.append(reward)
        done_buffer.append(done)
        state = next_state

        if done:
            state = env.reset()
            t_run =  t
            t = 0

            rew_buf.append(eps_rew)
            eps_rew = 0.0
            running_scores.append((i, np.mean(rew_buf)))  # i is the number of timestep so far

        ## For increasing the trainig time
        ttt = time.time()

        ## Update the policy after collecting a sufficient number of transition samples.
        buffer_size = state_buffer.get_size()
        if buffer_size >= min_batch_size:
            ## Randomly draw minibatch transition samples
            indexes = np.random.permutation(np.arange(buffer_size))[0:batch_size]
            s_batch = state_buffer.get_data(indexes)
            a_batch = action_buffer.get_data(indexes)
            sn_batch = nextstate_buffer.get_data(indexes)
            r_batch = reward_buffer.get_data(indexes)
            d_batch = done_buffer.get_data(indexes)

            ## Update the Q-network
            loss_q = learner.update_q(s_data=s_batch, a_data=a_batch, sn_data=sn_batch, r_data=r_batch, d_data=d_batch)

            ## Decide whether to update the entropy lower bound (kappa in the paper) or not
            if np.mod(i + 1, erate) == 0:
                beta_upd = 1
            else:
                beta_upd = 0

            ## Update the policy network
            loss_pol, eta, omega = learner.update_policy(s_data=s_batch, beta_upd=beta_upd)

            ## Record learning statistics
            loss_pol_n  = loss_pol_n + loss_pol
            loss_q_n    = loss_q_n + loss_q
            eta_n       = eta_n + eta
            omega_n     = omega_n + omega
            beta_n      = beta_n + learner.beta

        ## Increase the trainig time
        elapsed = elapsed + time.time() - ttt

    K.clear_session()
