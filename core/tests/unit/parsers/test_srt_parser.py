"""测试 SRT 解析器"""

from vid2note_core.parsers.srt_parser import SRTParser


def test_parse_simple():
    content = """1
00:00:01,000 --> 00:00:03,000
Hello world

2
00:00:05,500 --> 00:00:07,000
Second line
"""
    parser = SRTParser()
    items = parser.parse(content)
    assert len(items) == 2
    assert items[0].text == "Hello world"
    assert items[0].start_seconds == 1.0


def test_merge_short_sentences():
    content = """1
00:00:01,000 --> 00:00:02,000
Hello

2
00:00:02,500 --> 00:00:03,000
world
"""
    parser = SRTParser(merge_gap=1.0)
    items = parser.parse(content)
    assert len(items) == 1
    assert "Hello world" in items[0].text
