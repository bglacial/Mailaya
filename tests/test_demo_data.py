from app.demo_data import DEMO_MESSAGES, demo_messages


def test_demo_inbox_contains_500_distinct_fictional_messages():
    assert len(DEMO_MESSAGES) == 500
    assert len({(sender, subject) for sender, subject, _, _ in DEMO_MESSAGES}) == 500

    messages = demo_messages("2026-09-01", 500)
    assert len(messages) == 500
    assert len({message["graph_id"] for message in messages}) == 500
