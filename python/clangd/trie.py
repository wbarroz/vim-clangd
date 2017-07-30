TRIE_NODE_SIZE = ord('~') - ord(' ') + 1


class TrieNode(object):
    def __init__(self):
        self._children = [None] * TRIE_NODE_SIZE
        self._is_leaf = False
        self._leaf_data = []


class Trie(object):
    def __init__(self):
        self.root = self.getNode()

    def getNode(self):
        return TrieNode()

    def _charToIndex(self, c):
        return ord(c) - ord(' ')

    def insert(self, word, data=None):
        p_crawl = self.root
        length = len(word)
        for level in range(len(word)):
            index = self._charToIndex(word[level])
            if not p_crawl._children[index]:
                p_crawl._children[index] = self.getNode()
            p_crawl = p_crawl._children[index]

        p_crawl._is_leaf = True
        if data is not None:
            p_crawl._leaf_data.append(data)

    def _searchNode(self, word):
        p_crawl = self.root
        length = len(word)
        for level in range(len(word)):
            index = self._charToIndex(word[level])
            if not p_crawl._children[index]:
                return None
            p_crawl = p_crawl._children[index]
        if p_crawl is None:
            return None
        return p_crawl

    def search(self, word):
        p_crawl = self._searchNode(word)
        if not p_crawl or not p_crawl._is_leaf:
            return False
        return True

    def _iterNodes(self, p_crawl):
        results = []
        if p_crawl._is_leaf:
            results.extend(p_crawl._leaf_data)
        for i in range(TRIE_NODE_SIZE):
            child = p_crawl._children[i]
            if child:
                results.extend(self._iterNodes(child))
        return results

    def searchPrefix(self, word):
        p_crawl = self._searchNode(word)
        if not p_crawl:
            return []
        return self._iterNodes(p_crawl)
