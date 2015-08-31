import numpy as np
from skimage import img_as_float
import scipy.linalg
from scipy.interpolate import RectBivariateSpline
from skimage.filters import gaussian_filter, sobel

def active_contour_model(image, snake, alpha=0.01, beta=0.1,
                         w_line=0, w_edge=1, gamma=0.01,
                         bc='periodic', max_px_move=1.0,
                         max_iterations=2500, convergence=0.1):
    """Active contour model

    Active contours by fitting snakes to features of images. Supports single
    and multichannel 2D images. Snakes can be periodic (for segmentation) or
    have fixed and/or free ends.

    Parameters
    ----------
    image: (N, M) or (N, M, 3) ndarray
        Input image
    snake: (N, 2) ndarray
        Initialisation of snake.
    alpha: float, optional
        Snake length shape parameter
    beta: float, optional
        Snake smoothness shape parameter
    w_line: float, optional
        Controls attraction to brightness. Use negative values to attract to
        dark regions
    w_edge: float, optional
        Controls attraction to edges. Use negative values to repel snake from
        edges.
    gamma: flota, optional
        Excpliti time stepping parameter.
    bc: {'periodic', 'free', 'fixed'}, optional
        Boundary conditions for worm. 'periodic' attaches the two ends of the
         snake, 'fixed' holds the end-points in place, and'free' allows free
         movement of the ends. 'fixed' and 'free' can be combined by parsing
         'fixed-free', 'free-fixed'. Parsing 'fixed-fixed' or 'free-free'
         yields same behaviour as 'fixed' and 'free', respectively.
    max_px_move: float, optional
        Maximum pixel distance to move per iteration.
    max_iterations: int, optional
        Maximum iterations to optimize snake shape.
    convergence: float, optional
        Convergence criteria.

    Returns
    -------
    snake: (N, 2) ndarray
        Optimised snake, same shape as input parameter.

    References
    ----------
    .. [1]  Kass, M.; Witkin, A.; Terzopoulos, D. "Snakes: Active contour models". International Journal of Computer Vision 1 (4): 321 (1988).

    Examples
    --------
    >>> #from skimage.segmentation import active_contour_model
    >>> from skimage.draw import circle_perimeter
    >>> img = np.zeros((100, 100))
    >>> rr, cc = circle_perimeter(35, 45, 25)
    >>> img[rr, cc] = 1
    >>> img = gaussian_filter(img,2)
    >>> s = np.linspace(0,2*np.pi,100)
    >>> init = 50*np.array([np.cos(s),np.sin(s)]).T+50
    >>> snake = active_contour_model(img, init, w_edge=0, w_line=1)
    >>> int(np.mean(np.sqrt((45-snake[:,0])**2 + (35-snake[:,1])**2)))
    25

    """

    max_iterations = int(max_iterations)
    if max_iterations<=0:
        raise ValueError("max_iterations should be >0.")
    convergence_order = 10
    valid_bcs = ['periodic', 'free', 'fixed', 'free-fixed',
                 'fixed-free', 'fixed-fixed', 'free-free']
    if bc not in valid_bcs:
        raise ValueError("Invalid boundary condition.\n"+
                         "Should be one of: "+", ".join(valid_bcs)+'.')
    img = img_as_float(image)
    RGB = len(img.shape)==3

    # Find edges using sobel:
    if w_edge!=0:
        if RGB:
            edge = [sobel(img[:,:,0]),sobel(img[:,:,1]),sobel(img[:,:,2])]
        else:
            edge = [sobel(img)]
        for i in xrange(3 if RGB else 1):
            edge[i][0,:] = edge[i][1,:]
            edge[i][-1,:] = edge[i][-2,:]
            edge[i][:,0] = edge[i][:,1]
            edge[i][:,-1] = edge[i][:,-2]
    else:
        edge = [0]

    # Superimpose intensity and edge images:
    if RGB:
        img = w_line*np.sum(img,axis=2) \
            + w_edge*sum(edge)
    else:
        img = w_line*img + w_edge*edge[0]

    # Interpolate for smoothness:
    intp = RectBivariateSpline(np.arange(img.shape[1]),
            np.arange(img.shape[0]), img.T, kx=2, ky=2, s=0)

    x, y = snake[:, 0].copy(), snake[:, 1].copy()
    xsave = np.empty((convergence_order,len(x)))
    ysave = np.empty((convergence_order,len(x)))

    # Build snake shape matrix
    n = len(x)
    a = np.roll(np.eye(n), -1, axis=0) \
      + np.roll(np.eye(n), -1, axis=1) \
      - 2*np.eye(n)
    b = np.roll(np.eye(n), -2, axis=0) \
      + np.roll(np.eye(n), -2, axis=1) \
      - 4*np.roll(np.eye(n), -1, axis=0) \
      - 4*np.roll(np.eye(n), -1, axis=1) \
      + 6*np.eye(n)
    A = -alpha*a + beta*b

    # Impose boundary conditions different from periodic:
    sfixed = False
    if bc.startswith('fixed'):
        A[0, :] = 0
        A[1, :] = 0
        A[1, :3] = [1, -2, 1]
        sfixed = True
    efixed = False
    if bc.endswith('fixed'):
        A[-1, :] = 0
        A[-2, :] = 0
        A[-2, -3:] = [1, -2, 1]
        efixed = True
    sfree = False
    if bc.startswith('free'):
        A[0, :] = 0
        A[0, :3] = [1, -2, 1]
        A[1, :] = 0
        A[1, :4] = [-1, 3, -3, 1]
        sfree = True
    efree = False
    if bc.endswith('free'):
        A[-1, :] = 0
        A[-1, -3:] = [1, -2, 1]
        A[-2, :] = 0
        A[-2, -4:] = [-1, 3, -3, 1]
        efree = True

    # Only one inversion is needed:
    inv = scipy.linalg.inv(A+gamma*np.eye(n))

    # Explcit time stepping for image energy minimization:
    for i in xrange(max_iterations):
        fx = intp(x, y, dx=1, grid=False)
        fy = intp(x, y, dy=1, grid=False)
        if sfixed:
            fx[0] = 0
            fy[0] = 0
        if efixed:
            fx[-1] = 0
            fy[-1] = 0
        if sfree:
            fx[0] *= 2
            fy[0] *= 2
        if efree:
            fx[-1] *= 2
            fy[-1] *= 2
        xn = np.dot(inv, gamma*x + fx)
        yn = np.dot(inv, gamma*y + fy)

        # Movements are capped to max_px_move per iteration:
        dx = max_px_move*np.tanh(xn-x)
        dy = max_px_move*np.tanh(yn-y)
        if sfixed:
            dx[0] = 0
            dy[0] = 0
        if efixed:
            dx[-1] = 0
            dy[-1] = 0
        x[:] += dx
        y[:] += dy

        # Convergence criteria:
        j = i%(convergence_order+1)
        if j<convergence_order:
            xsave[j,:] = x
            ysave[j,:] = y
        else:
            dist = np.min(np.max(np.abs(xsave-x[None, :])
                + np.abs(ysave-y[None, :]), 1))
            if dist < convergence:
                break

    return np.array([x, y]).T