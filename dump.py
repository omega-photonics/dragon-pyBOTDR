import numpy as np
from datetime import datetime
from os import mkdir, path

def mydump(up_0, up_1, down_0, down_1):
    savepath = "/home/gleb/dumps/" + datetime.now().isoformat().replace(":", "-")
    mkdir(savepath)
    np.savetxt(path.join(savepath, "up_0.txt"), up_0)
    np.savetxt(path.join(savepath, "down_0.txt"), down_0)
    np.savetxt(path.join(savepath, "up_1.txt"), up_1)
    np.savetxt(path.join(savepath, "down_1.txt"), down_1)