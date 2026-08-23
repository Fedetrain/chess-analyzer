# test_chess_utils.py
import unittest
import chess
from chess_utils import ChessUtils, AnalysisCache

class TestChessUtils(unittest.TestCase):
    
    def setUp(self):
        self.utils = ChessUtils()
        self.board = chess.Board()
    
    def test_legal_moves_cached(self):
        fen = self.board.fen()
        moves1 = self.utils.get_legal_moves_cached(fen)
        moves2 = self.utils.get_legal_moves_cached(fen)
        self.assertEqual(moves1, moves2)
        self.assertGreater(len(moves1), 0)
    
    def test_cache_different_positions(self):
        fen1 = self.board.fen()
        moves1 = self.utils.get_legal_moves_cached(fen1)
        
        # Make a move
        self.board.push(chess.Move.from_uci("e2e4"))
        fen2 = self.board.fen()
        moves2 = self.utils.get_legal_moves_cached(fen2)
        
        self.assertNotEqual(moves1, moves2)

class TestAnalysisCache(unittest.TestCase):
    
    def setUp(self):
        self.cache = AnalysisCache(max_size=3, timeout_seconds=1)
    
    def test_basic_operations(self):
        self.cache.set("key1", "value1")
        self.assertEqual(self.cache.get("key1"), "value1")
        
        self.cache.set("key2", "value2")
        self.cache.set("key3", "value3")
        self.assertEqual(self.cache.get("key3"), "value3")
    
    def test_lru_eviction(self):
        self.cache.set("key1", "value1")
        self.cache.set("key2", "value2") 
        self.cache.set("key3", "value3")
        self.cache.set("key4", "value4")  # Should evict key1
        
        self.assertIsNone(self.cache.get("key1"))
        self.assertEqual(self.cache.get("key2"), "value2")
    
    def test_timeout(self):
        import time
        self.cache.set("key1", "value1")
        time.sleep(1.1)  # Wait longer than timeout
        self.assertIsNone(self.cache.get("key1"))

if __name__ == "__main__":
    unittest.main()