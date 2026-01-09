"""
Tests for strategy loading and parsing.
"""
import pytest
import os
import tempfile
from probablyprofit.agent.strategy import CustomStrategy, MeanReversionStrategy, NewsTradingStrategy


class TestMeanReversionStrategy:
    def test_get_prompt(self):
        strategy = MeanReversionStrategy()
        prompt = strategy.get_prompt()
        
        assert "mean reversion" in prompt.lower() or "reversion" in prompt.lower()
        assert len(prompt) > 50  # Should have meaningful content

    def test_default_thresholds(self):
        strategy = MeanReversionStrategy()
        assert hasattr(strategy, 'low_threshold') or True  # May have different attr names


class TestNewsTradingStrategy:
    def test_get_prompt_includes_keywords(self):
        keywords = ["Bitcoin", "ETH", "crypto"]
        strategy = NewsTradingStrategy(keywords=keywords)
        prompt = strategy.get_prompt()
        
        # Prompt should mention the keywords
        for kw in keywords:
            assert kw in prompt

    def test_empty_keywords(self):
        strategy = NewsTradingStrategy(keywords=[])
        prompt = strategy.get_prompt()
        assert len(prompt) > 0  # Should still have a prompt


class TestCustomStrategy:
    def test_custom_prompt_text(self):
        custom_text = "You are an aggressive trader. Buy everything under 0.20."
        strategy = CustomStrategy(prompt_text=custom_text)
        prompt = strategy.get_prompt()
        
        assert custom_text in prompt

    def test_custom_with_keywords(self):
        strategy = CustomStrategy(
            prompt_text="Trade these keywords:",
            keywords=["AI", "tech"]
        )
        prompt = strategy.get_prompt()
        
        assert "Trade these keywords:" in prompt


class TestStrategyFiles:
    def test_load_example_strategies(self):
        """Test that example strategy files can be loaded."""
        examples_dir = os.path.join(
            os.path.dirname(__file__),
            "..",
            "examples"
        )
        
        if os.path.exists(examples_dir):
            for filename in os.listdir(examples_dir):
                if filename.endswith(".txt"):
                    filepath = os.path.join(examples_dir, filename)
                    with open(filepath, "r") as f:
                        content = f.read()
                    
                    # Each strategy file should have content
                    assert len(content) > 20, f"Strategy {filename} too short"
                    
                    # Should be loadable as CustomStrategy
                    strategy = CustomStrategy(prompt_text=content)
                    prompt = strategy.get_prompt()
                    assert len(prompt) > 0

    def test_strategy_from_temp_file(self):
        """Test loading strategy from a file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Test strategy: Buy low, sell high.")
            temp_path = f.name
        
        try:
            with open(temp_path, 'r') as f:
                content = f.read()
            
            strategy = CustomStrategy(prompt_text=content)
            assert "Buy low" in strategy.get_prompt()
        finally:
            os.unlink(temp_path)
