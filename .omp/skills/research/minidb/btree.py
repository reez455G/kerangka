"""
btree.py — B-Tree Order-t (Minimum Degree)
============================================

B-Tree adalah struktur data pohon yang seimbang (balanced), dirancang khusus
untuk sistem yang membaca/menulis data dalam blok besar (disk pages).

Properti utama B-Tree order-t:
  • Setiap node (kecuali root) punya minimal t-1 key dan maksimal 2t-1 key.
  • Setiap internal node punya minimal t child dan maksimal 2t child.
  • Semua leaf berada di level yang sama → tinggi pohon selalu O(log n).
  • Operasi search/insert/delete: O(log n).

Perbedaan dengan BST/AVL:
  BST dan AVL menyimpan satu key per node → dalam skenario disk,
  setiap node = satu disk read (mahal). B-Tree menyimpan BANYAK key
  per node → satu disk read membawa banyak key (efisien I/O).

Implementasi ini:
  • Key: integer atau string (comparable)
  • Value: arbitrary Python object
  • Mendukung duplicate key (untuk secondary index)
  • Range query: range_search(low, high) → list[(key, value)]
  • Iterasi in-order (ascending)

Referensi: CLRS Chapter 18 — B-Trees
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Generic, Iterator, List, Optional, Tuple, TypeVar

K = TypeVar("K")  # Key type — harus comparable (int, str)


# ─────────────────────────────────────────────────────────────────────────────
# Node
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class BTreeNode:
    """
    Satu node dalam B-Tree.

    keys     : list of (key, value) pairs, urut ascending by key
    children : list of child BTreeNode (len = len(keys)+1 untuk internal node)
    is_leaf  : True jika node ini adalah leaf (tidak punya anak)
    """
    keys: List[Tuple[Any, Any]] = field(default_factory=list)
    children: List["BTreeNode"] = field(default_factory=list)
    is_leaf: bool = True

    def __repr__(self) -> str:
        ks = [k for k, _ in self.keys]
        return f"BTreeNode(keys={ks}, leaf={self.is_leaf})"


# ─────────────────────────────────────────────────────────────────────────────
# B-Tree
# ─────────────────────────────────────────────────────────────────────────────
class BTree:
    """
    B-Tree dengan minimum degree t.

    Penggunaan:
        tree = BTree(t=3)          # order-3: max 5 key per node
        tree.insert(10, "Alice")
        tree.insert(20, "Bob")
        val = tree.search(10)      # → "Alice"
        tree.delete(10)
        pairs = tree.range_search(5, 25)  # → [(10, "Alice"), (20, "Bob")]
    """

    def __init__(self, t: int = 2) -> None:
        if t < 2:
            raise ValueError("Minimum degree t harus >= 2")
        self.t = t                          # minimum degree
        self.max_keys = 2 * t - 1          # max keys per node
        self.min_keys = t - 1              # min keys (kecuali root)
        self.root: BTreeNode = BTreeNode(is_leaf=True)
        self._size = 0                      # jumlah total (key, value) pairs

    # ── Public API ────────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return self._size

    def search(self, key: Any) -> Optional[Any]:
        """
        Cari key. Return value pertama yang cocok, atau None jika tidak ada.
        Kompleksitas: O(t · log_t(n))
        """
        result = self._search_node(self.root, key)
        return result[1] if result else None

    def search_all(self, key: Any) -> List[Any]:
        """Return semua value untuk key yang sama (untuk duplicate keys)."""
        results: List[Any] = []
        self._collect_by_key(self.root, key, results)
        return results

    def insert(self, key: Any, value: Any) -> None:
        """
        Sisipkan (key, value).
        Jika root penuh, split root terlebih dahulu (meningkatkan tinggi pohon).
        Kompleksitas: O(t · log_t(n))
        """
        root = self.root
        if len(root.keys) == self.max_keys:
            # Root penuh → buat root baru, split root lama menjadi child
            new_root = BTreeNode(is_leaf=False)
            new_root.children.append(self.root)
            self._split_child(new_root, 0)
            self.root = new_root

        self._insert_non_full(self.root, key, value)
        self._size += 1

    def delete(self, key: Any) -> bool:
        """
        Hapus SATU entry dengan key ini. Return True jika ditemukan dan dihapus.
        Kompleksitas: O(t · log_t(n))

        Algoritma delete B-Tree (CLRS):
          Case 1: key di leaf → hapus langsung
          Case 2: key di internal node → ganti dengan predecessor/successor
          Case 3: key tidak di node ini → turun ke anak, pastikan anak ≥ t key
        """
        if not self.root.keys:
            return False

        deleted = self._delete(self.root, key)
        if deleted:
            self._size -= 1
            # Jika root menjadi kosong setelah delete, turunkan tinggi
            if not self.root.keys and not self.root.is_leaf:
                self.root = self.root.children[0]
        return deleted

    def range_search(self, low: Any, high: Any) -> List[Tuple[Any, Any]]:
        """
        Return semua (key, value) di mana low <= key <= high, urut ascending.
        Kompleksitas: O(t · log_t(n) + k) di mana k = jumlah hasil
        """
        results: List[Tuple[Any, Any]] = []
        self._range_search(self.root, low, high, results)
        return results

    def inorder(self) -> Iterator[Tuple[Any, Any]]:
        """Generator: yield semua (key, value) in ascending key order."""
        yield from self._inorder(self.root)

    def height(self) -> int:
        """Tinggi pohon (root = level 1)."""
        h = 1
        node = self.root
        while not node.is_leaf:
            node = node.children[0]
            h += 1
        return h

    # ── Internal: Search ──────────────────────────────────────────────────────

    def _search_node(
        self, node: BTreeNode, key: Any
    ) -> Optional[Tuple[Any, Any]]:
        """Rekursif: cari key di subtree yang di-root oleh node."""
        i = 0
        # Scan ke kanan sampai keys[i] >= key
        while i < len(node.keys) and key > node.keys[i][0]:
            i += 1

        if i < len(node.keys) and key == node.keys[i][0]:
            return node.keys[i]   # ditemukan

        if node.is_leaf:
            return None           # tidak ada di pohon

        return self._search_node(node.children[i], key)

    def _collect_by_key(
        self, node: BTreeNode, key: Any, results: List[Any]
    ) -> None:
        """Kumpulkan semua value dengan key yang cocok (termasuk duplikat)."""
        i = 0
        while i < len(node.keys):
            if not node.is_leaf:
                self._collect_by_key(node.children[i], key, results)
            if node.keys[i][0] == key:
                results.append(node.keys[i][1])
            elif node.keys[i][0] > key:
                return
            i += 1
        if not node.is_leaf:
            self._collect_by_key(node.children[i], key, results)

    # ── Internal: Insert ──────────────────────────────────────────────────────

    def _split_child(self, parent: BTreeNode, i: int) -> None:
        """
        Split child[i] dari parent yang sudah penuh (2t-1 keys) menjadi dua.

        Sebelum:  parent [...] child[i] = [k0..k(2t-2)]
        Sesudah:  parent [..., k(t-1), ...] dengan child[i] = [k0..k(t-2)]
                  dan child baru [k(t)..k(2t-2)]

        Key tengah (k(t-1)) naik ke parent.
        """
        t = self.t
        full_child = parent.children[i]
        new_child = BTreeNode(is_leaf=full_child.is_leaf)

        # Key tengah yang naik ke parent
        mid_key = full_child.keys[t - 1]

        # Belah keys: kiri t-1 key, kanan t-1 key
        new_child.keys = full_child.keys[t:]       # [t .. 2t-2]
        full_child.keys = full_child.keys[:t - 1]  # [0 .. t-2]

        # Belah children jika bukan leaf
        if not full_child.is_leaf:
            new_child.children = full_child.children[t:]
            full_child.children = full_child.children[:t]

        # Sisipkan mid_key ke parent dan tambah child baru
        parent.keys.insert(i, mid_key)
        parent.children.insert(i + 1, new_child)

    def _insert_non_full(self, node: BTreeNode, key: Any, value: Any) -> None:
        """
        Sisipkan (key, value) ke subtree yang di-root oleh node.
        Precondition: node tidak penuh (< 2t-1 keys).
        """
        i = len(node.keys) - 1

        if node.is_leaf:
            # Cari posisi insert dengan geser key lebih besar ke kanan
            node.keys.append(None)  # type: ignore[arg-type]  # placeholder
            while i >= 0 and key < node.keys[i][0]:
                node.keys[i + 1] = node.keys[i]
                i -= 1
            node.keys[i + 1] = (key, value)
        else:
            # Temukan child yang tepat
            while i >= 0 and key < node.keys[i][0]:
                i -= 1
            i += 1  # indeks child yang akan dituruni

            # Jika child penuh, split dulu
            if len(node.children[i].keys) == self.max_keys:
                self._split_child(node, i)
                # Setelah split, mid key naik ke node; tentukan child mana
                if key > node.keys[i][0]:
                    i += 1

            self._insert_non_full(node.children[i], key, value)

    # ── Internal: Delete ──────────────────────────────────────────────────────

    def _delete(self, node: BTreeNode, key: Any) -> bool:
        """
        Hapus satu kemunculan key dari subtree node.
        Return True jika berhasil.
        """
        t = self.t
        i = 0
        # Cari posisi key atau child yang tepat
        while i < len(node.keys) and key > node.keys[i][0]:
            i += 1

        if i < len(node.keys) and key == node.keys[i][0]:
            # ── Key ditemukan di node ini ─────────────────────────────────
            if node.is_leaf:
                # Case 1: Leaf → hapus langsung
                node.keys.pop(i)
                return True
            else:
                # Case 2: Internal node
                left_child = node.children[i]
                right_child = node.children[i + 1]

                if len(left_child.keys) >= t:
                    # Case 2a: Left child punya cukup key
                    # Ganti node.keys[i] dengan predecessor (key terbesar di left)
                    pred = self._get_max(left_child)
                    node.keys[i] = pred
                    return self._delete(left_child, pred[0])

                elif len(right_child.keys) >= t:
                    # Case 2b: Right child punya cukup key
                    # Ganti node.keys[i] dengan successor (key terkecil di right)
                    succ = self._get_min(right_child)
                    node.keys[i] = succ
                    return self._delete(right_child, succ[0])

                else:
                    # Case 2c: Kedua anak hanya punya t-1 key → merge
                    self._merge_children(node, i)
                    return self._delete(left_child, key)
        else:
            # ── Key tidak di node ini → turun ke child[i] ─────────────────
            if node.is_leaf:
                return False  # Key tidak ada di pohon

            # Pastikan child[i] punya minimal t key sebelum turun
            child = node.children[i]
            if len(child.keys) < t:
                self._fill(node, i)
                # Setelah fill, indeks mungkin berubah jika terjadi merge
                # Cari ulang posisi yang tepat
                i = 0
                while i < len(node.keys) and key > node.keys[i][0]:
                    i += 1
                if i < len(node.keys) and key == node.keys[i][0]:
                    return self._delete(node, key)  # key mungkin sudah naik
                child = node.children[i]

            return self._delete(child, key)

    def _get_max(self, node: BTreeNode) -> Tuple[Any, Any]:
        """Key terbesar di subtree (paling kanan dari leaf paling kanan)."""
        while not node.is_leaf:
            node = node.children[-1]
        return node.keys[-1]

    def _get_min(self, node: BTreeNode) -> Tuple[Any, Any]:
        """Key terkecil di subtree."""
        while not node.is_leaf:
            node = node.children[0]
        return node.keys[0]

    def _merge_children(self, parent: BTreeNode, i: int) -> None:
        """
        Merge parent.children[i] dan parent.children[i+1].
        Key pemisah parent.keys[i] turun ke child yang di-merge.
        Hasil: satu child dengan 2t-1 keys.
        """
        left = parent.children[i]
        right = parent.children[i + 1]

        # Key pemisah dari parent turun
        left.keys.append(parent.keys.pop(i))
        # Gabungkan semua key dari right ke left
        left.keys.extend(right.keys)
        # Gabungkan children jika bukan leaf
        if not left.is_leaf:
            left.children.extend(right.children)
        # Hapus right child dari parent
        parent.children.pop(i + 1)

    def _fill(self, parent: BTreeNode, i: int) -> None:
        """
        Pastikan parent.children[i] punya minimal t keys.
        Strategi: pinjam dari saudara kiri/kanan, atau merge.
        """
        t = self.t
        child = parent.children[i]

        if i > 0 and len(parent.children[i - 1].keys) >= t:
            # Pinjam dari saudara kiri
            self._borrow_from_left(parent, i)
        elif i < len(parent.children) - 1 and len(parent.children[i + 1].keys) >= t:
            # Pinjam dari saudara kanan
            self._borrow_from_right(parent, i)
        else:
            # Merge dengan saudara
            if i < len(parent.children) - 1:
                self._merge_children(parent, i)
            else:
                self._merge_children(parent, i - 1)

    def _borrow_from_left(self, parent: BTreeNode, i: int) -> None:
        """Geser satu key dari saudara kiri melalui parent."""
        child = parent.children[i]
        left_sibling = parent.children[i - 1]

        # Key dari parent turun ke child (di posisi paling kiri)
        child.keys.insert(0, parent.keys[i - 1])
        # Key terbesar dari saudara kiri naik ke parent
        parent.keys[i - 1] = left_sibling.keys.pop(-1)
        # Pindahkan child paling kanan dari saudara jika bukan leaf
        if not child.is_leaf:
            child.children.insert(0, left_sibling.children.pop(-1))

    def _borrow_from_right(self, parent: BTreeNode, i: int) -> None:
        """Geser satu key dari saudara kanan melalui parent."""
        child = parent.children[i]
        right_sibling = parent.children[i + 1]

        # Key dari parent turun ke child (di posisi paling kanan)
        child.keys.append(parent.keys[i])
        # Key terkecil dari saudara kanan naik ke parent
        parent.keys[i] = right_sibling.keys.pop(0)
        # Pindahkan child paling kiri dari saudara jika bukan leaf
        if not child.is_leaf:
            child.children.append(right_sibling.children.pop(0))

    # ── Internal: Range & Iteration ───────────────────────────────────────────

    def _range_search(
        self, node: BTreeNode, low: Any, high: Any, results: List[Tuple[Any, Any]]
    ) -> None:
        """Kumpulkan semua (key, value) di mana low <= key <= high."""
        i = 0
        while i < len(node.keys):
            if not node.is_leaf and node.keys[i][0] > low:
                self._range_search(node.children[i], low, high, results)
            if low <= node.keys[i][0] <= high:
                results.append(node.keys[i])
            elif node.keys[i][0] > high:
                return
            i += 1
        if not node.is_leaf:
            self._range_search(node.children[i], low, high, results)

    def _inorder(self, node: BTreeNode) -> Iterator[Tuple[Any, Any]]:
        """In-order traversal (ascending)."""
        for i, kv in enumerate(node.keys):
            if not node.is_leaf:
                yield from self._inorder(node.children[i])
            yield kv
        if not node.is_leaf:
            yield from self._inorder(node.children[-1])

    # ── Debug ─────────────────────────────────────────────────────────────────

    def visualize(self, node: Optional[BTreeNode] = None, level: int = 0) -> str:
        """ASCII dump pohon untuk debugging."""
        if node is None:
            node = self.root
        indent = "  " * level
        ks = [k for k, _ in node.keys]
        lines = [f"{indent}[{', '.join(str(k) for k in ks)}]"]
        for child in node.children:
            lines.append(self.visualize(child, level + 1))
        return "\n".join(lines)
