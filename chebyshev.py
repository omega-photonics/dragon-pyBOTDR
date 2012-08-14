from __future__ import division
from scipy.linalg import fblas
import numpy as np
from numpy.core.umath_tests import inner1d
from time import time

def main(*files):
    from matplotlib import pyplot as plt
    RefChannel = 3170
    Channel = 1700
    ChebOrder = 40
    print("Loading data ...")

    A = [np.loadtxt(file) for file in files]
    print("Searching maximums ...")
    results = [calc_argmax(data) for data in A]
    for res in results:
        res -= res[RefChannel]
    M = [Ai.max(axis=-1) for Ai in A]
    ind = (M[0] * results[0] + M[1] * results[1]) / (M[0] + M[1])
    indi = (M[2] * results[2] + M[3] * results[3]) / (M[2] + M[3])
    plt.figure(1)
    start = 1500
    end = 3500
    x = np.arange(start, end)
    ls = [plt.plot(res[start:end]) for res in results]

    plt.figure(2)
    plt.plot(ind[start:end])
    plt.plot(indi[start:end])

    plt.figure(3)
    plt.plot(indi[start:end] - ind[start:end])
    plt.show()

def calc_argmax(data):
    T = data.shape[-1]
    N = T // 5
    t0 = time()
    C, D, DD = dcheb(T, N)
    K = fblas.dgemm(alpha=1., b=data.T, a=C.T).T
    apr = fblas.dgemm(alpha=1., a=C.T, b=K.T, trans_a=True).T
    argmaxs = apr.argmax(axis=-1)
#    Ds = DD[argmaxs]  # makes copies
#    DDs = DD[argmaxs]
#    pers = inner1d(K, Ds) / inner1d(K, DDs) 
    pers = np.empty_like(argmaxs, dtype=float)
    for i, ax in enumerate(argmaxs):   # does not make copies. slower.
        pers[i] = fblas.ddot(K[i], D[ax]) / fblas.ddot(K[i], DD[ax])
    pers[pers > 1] = 0
    return argmaxs - pers

def text_apr(data, d1data=None, d2data=None):
    N = 10 
    T = data.shape[-1]
    C, D, DD = dcheb(T, N)
    K = fblas.dgemm(alpha=1., a=data.T, b=C.T, trans_a=True)
    apr = fblas.dgemm(alpha=1., a=C.T, b=K, trans_a=False, trans_b=True).T
    d1apr = fblas.dgemm(alpha=1., a=D.T, b=K, trans_a=False, trans_b=True).T
    d2apr = fblas.dgemm(alpha=1., a=DD.T, b=K, trans_a=False, trans_b=True).T
    print ((data - apr) ** 2).sum() / (data**2).sum()
    if d1data is not None:
        print ((d1data - d1apr) ** 2).sum() / (d1data**2).sum()
    if d2data is not None:
        print ((d2data - d2apr) ** 2).sum() / (d2data**2).sum()

def dcheb(T, N):
    C   = np.empty((N, T), dtype=float, order='F')
    D1C = np.empty((N, T), dtype=float, order='F')
    D2C = np.empty((N, T), dtype=float, order='F')
    
    t = np.arange(T)

    C[0] = 1.
    D1C[0] = 0.
    D2C[0] = 0.
    
    if N == 1:
        C /= T ** .5
        D1C /= T ** .5
        D2C /= T ** .5
        return C, D1C, D2C

    C[1] = 1. - T + 2 * t
    D1C[1] = 2.
    D2C[1] = 0.
    
    br2 = 2 * t - T + 1
    for n in range(1, N - 1):
        br1 = (2 * n + 1)
        br3 = n * (T * T - n * n)
        
        C[n + 1] = br1 * br2 * C[n] - br3 * C[n - 1]
        D1C[n + 1] = br1 * (2 * C[n] + br2 * D1C[n]) - br3 * D1C[n - 1]
        D2C[n + 1] = br1 * (4 * D1C[n] + br2 * D2C[n]) - br3 * D2C[n - 1]
        
        C[n + 1] /= n + 1
        D1C[n + 1] /= n + 1 
        D2C[n + 1] /= n + 1
    
    norm = T ** .5
    for n in range(1, N + 1):
        C[n - 1] /= norm
        D1C[n - 1] /= norm
        D2C[n - 1] /= norm
        norm *= ((T * T - n * n) * (2 * n - 1) / (2 * n + 1)) ** .5 
    
    return C.T, D1C.T, D2C.T


if __name__ == '__main__':
    import sys
    from time import time
    files = sys.argv[1:]
    if files:
        main(*files)
    else:
        sp_len = 200
        n_sp = int(1e5)
        shift = np.linspace(0.99 / sp_len , 40 / sp_len, n_sp).reshape(n_sp ,1)
        x, dx = np.linspace(-1, 1, sp_len, retstep=True)
        print "shifts in steps:\n", shift / dx
        x = np.array([x] * n_sp)
        x = x.reshape(-1, sp_len)
        x += shift
        sp = np.exp(-x * x)
        dsp = -2 * x * sp * dx 
        d2sp = -2 * sp + 4 * x * x * sp
        d2sp *= dx ** 2
        print "start processing {} spectra with {} points per spectrum".format(
                n_sp, sp_len)
        t = time()
        res = calc_argmax(sp)
        print "{:.4f} total (may be more than expected)".format(time() - t)
        xmaxs = [x[i, int(res[i])] + dx * (res[i] - int(res[i]))
                  for i in range(n_sp)]
        print "maximum error in steps {}".format(max(map(abs, xmaxs)) / dx)
