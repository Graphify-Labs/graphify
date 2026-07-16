# Helpers for current-flow betweenness and current-flow closeness
# Lazy computations for inverse Laplacian and flow-matrix rows.
import networkx as nx


@nx._dispatchable(edge_attrs="weight")
def flow_matrix_row(G, weight=None, dtype=float, solver="lu"):
    # Generate a row of the current-flow matrix
    import numpy as np

    solvername = {
        "full": FullInverseLaplacian,
        "lu": SuperLUInverseLaplacian,
        "cg": CGInverseLaplacian,
    }
    n = G.number_of_nodes()
    L = nx.laplacian_matrix(G, nodelist=range(n), weight=weight).asformat("csc")
    L = L.astype(dtype)
    C = solvername[solver](L, dtype=dtype)  # initialize solver
    w = C.w  # w is the Laplacian matrix width
    # row-by-row flow matrix
    for u, v in sorted(sorted((u, v)) for u, v in G.edges()):
        B = np.zeros(w, dtype=dtype)
        c = G[u][v].get(weight, 1.0)
        B[u % w] = c
        B[v % w] = -c
        # get only the rows needed in the inverse laplacian
        # and multiply to get the flow matrix row
        row = B @ C.get_rows(u, v)
        yield row, (u, v)


# Class to compute the inverse laplacian only for specified rows
# Allows computation of the current-flow matrix without storing entire
# inverse laplacian matrix
class InverseLaplacian:
    def __init__(self, L, width=None, dtype=None):
        global np
        import numpy as np

        (n, n) = L.shape
        self.dtype = dtype
        self.n = n
        if width is None:
            self.w = self.width(L)
        else:
            self.w = width
        self.C = np.zeros((self.w, n), dtype=dtype)
        self.L1 = L[1:, 1:]
        self.init_solver(L)

    def init_solver(self, L):
        pass

    def solve(self, r):
        raise nx.NetworkXError("Implement solver")

    def solve_inverse(self, r):
        raise nx.NetworkXError("Implement solver")

    def get_rows(self, r1, r2):
        for r in range(r1, r2 + 1):
            self.C[r % self.w, 1:] = self.solve_inverse(r)
        return self.C

    def get_row(self, r):
        self.C[r % self.w, 1:] = self.solve_inverse(r)
        return self.C[r % self.w]

    def width(self, L):
        m = 0
        for i, row in enumerate(L):
            w = 0
            y = np.nonzero(row)[-1]
            if len(y) > 0:
                v = y - i
                w = v.max() - v.min() + 1
                m = max(w, m)
        return m


class FullInverseLaplacian(InverseLaplacian):
    def init_solver(self, L):
        self.IL = np.zeros(L.shape, dtype=self.dtype)
        self.IL[1:, 1:] = np.linalg.inv(self.L1.todense())

    def solve(self, rhs):
        s = np.zeros(rhs.shape, dtype=self.dtype)
        s = self.IL @ rhs
        return s

    def solve_inverse(self, r):
        return self.IL[r, 1:]


class SuperLUInverseLaplacian(InverseLaplacian):
    def init_solver(self, L):
        import scipy as sp

        self.lusolve = sp.sparse.linalg.factorized(self.L1.tocsc())

    def solve_inverse(self, r):
        rhs = np.zeros(self.n, dtype=self.dtype)
        rhs[r] = 1
        return self.lusolve(rhs[1:])

    def solve(self, rhs):
        s = np.zeros(rhs.shape, dtype=self.dtype)
        s[1:] = self.lusolve(rhs[1:])
        return s


class CGInverseLaplacian(InverseLaplacian):
    def init_solver(self, L):
        global sp
        import scipy as sp

        ilu = sp.sparse.linalg.spilu(self.L1.tocsc())
        n = self.n - 1
        self.M = sp.sparse.linalg.LinearOperator(shape=(n, n), matvec=ilu.solve)

    def solve(self, rhs):
        s = np.zeros(rhs.shape, dtype=self.dtype)
        s[1:] = sp.sparse.linalg.cg(self.L1, rhs[1:], M=self.M, atol=0)[0]
        return s

    def solve_inverse(self, r):
        rhs = np.zeros(self.n, self.dtype)
        rhs[r] = 1
        return sp.sparse.linalg.cg(self.L1, rhs[1:], M=self.M, atol=0)[0]
