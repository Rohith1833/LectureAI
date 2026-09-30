import pytest
from app.services.artifact.artifact_planner import split_content_into_bounded_segments

def test_oversized_single_sentence_subdivision_without_truncation():
    """
    Verify that an oversized single sentence without punctuation/paragraph breaks
    is subdivided into bounded segments (<= max_chars) without silent truncation.
    """
    max_chars = 100
    # A single sentence with words but no sentence-terminating punctuation
    single_sentence = " ".join([f"word_{i:03d}" for i in range(100)]) # ~900 characters
    
    parts = split_content_into_bounded_segments(single_sentence, max_chars=max_chars)
    
    # Must have multiple parts
    assert len(parts) > 1, "Expected multiple parts for oversized sentence"
    
    # Every segment must be <= max_chars
    for suffix, text in parts:
        assert len(text) <= max_chars, f"Segment exceeded max_chars ({len(text)} > {max_chars}): {text}"
        assert text.strip(), "Segment must not be empty"
        assert "Part " in suffix, "Suffix must contain Part numbering"
        
    # Reconstructed words must match original words (no silent loss/truncation)
    reconstructed_words = []
    for _, text in parts:
        reconstructed_words.extend(text.split())
        
    original_words = single_sentence.split()
    assert reconstructed_words == original_words, "Content was altered or truncated during subdivision"

def test_oversized_unbroken_string_subdivision():
    """
    Verify that an unbroken monolithic string (e.g. raw DNA or hash > max_chars)
    is cleanly partitioned into bounded segments without crashing or truncation.
    """
    max_chars = 50
    monolithic_string = "A" * 230
    
    parts = split_content_into_bounded_segments(monolithic_string, max_chars=max_chars)
    assert len(parts) == 5 # 50 * 4 + 30 = 230
    
    reconstructed = "".join([text for _, text in parts])
    assert reconstructed == monolithic_string
