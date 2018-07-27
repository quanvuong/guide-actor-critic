import os
import pickle


TOP_RES_DIR = 'res/'


def get_saved_path(args):
    hp_as_str = args.stringify_hp(args.hp)

    dir = TOP_RES_DIR + hp_as_str + '/' + args.hp[0]

    os.makedirs(dir, exist_ok=True)

    return dir + '/' + str(args.hp[1])


def get_graph_f(args):
    return get_saved_path(args) + '.png'


def get_pkl_f(args):
    return get_saved_path(args) + '.pkl'


def pkl_res(obj, args):
    # Format of path
    # is res -> hp string -> env -> {seed}.pkl

    pkl_f = get_pkl_f(args)

    with open(pkl_f, 'wb+') as f:
        pickle.dump(obj, f)


def load_pkl_file(path):
    with open(path, 'rb') as f:
        return pickle.load(f)


def get_oa_rand_res(dir):
    """Get results for each seed for each environment in this dir"""
    ENVS = ["InvertedPendulum-v2", "Hopper-v2", "InvertedDoublePendulum-v2", "Reacher-v2",
            "Swimmer-v2", "Walker2d-v2", "HalfCheetah-v2",
            'Ant-v2', 'Humanoid-v2', 'HumanoidStandup-v2']

    SEEDS = [i for i in range(0, 5)]
    NUM_SEEDS = len(SEEDS)

    reses = {}
    for env in ENVS:
        reses[env] = []

    for env_i, env in enumerate(ENVS):
        start_i = env_i * NUM_SEEDS
        for seed_i in range(start_i, start_i + NUM_SEEDS):
            path = dir + 'res_' + str(seed_i) + '.pickled'
            res = load_pkl_file(path)

            reses[env].append(res)

    return reses
