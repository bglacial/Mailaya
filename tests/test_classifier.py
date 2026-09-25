from app.classifier import DemoClassifier, _extract_choice, _extract_noul, _extract_score


def sample_email(**overrides):
    email = {
        "graph_id": "mail-1",
        "sender_name": "Service achats",
        "sender_address": "achats@example.com",
        "subject": "Validation du devis avant vendredi",
        "body_preview": "Merci de confirmer le devis avant vendredi midi.",
    }
    email.update(overrides)
    return email


def test_demo_classifier_returns_all_requested_outputs():
    result = DemoClassifier().classify(sample_email())

    assert result["category"] in result["category_scores"]
    assert abs(sum(result["category_scores"].values()) - 1.0) < 0.01
    assert 0 <= result["priority_score"] <= 100
    assert 0 <= result["spam_score"] <= 100
    assert 0 <= result["action_score"] <= 100
    assert result["duration_ms"] > 0


def test_laya_answer_adapters_accept_public_output_shape():
    choice, scores = _extract_choice(
        {"choice": "Finance", "probabilities": {"Finance": 0.78, "Support": 0.22}}
    )

    assert choice == "Finance"
    assert scores == {"Finance": 0.78, "Support": 0.22}
    assert _extract_score({"score": 1.5}) == 50.0
    assert _extract_noul({"noul": 0.81234}) == 0.8123


def test_spam_demo_signal_is_monotonic():
    classifier = DemoClassifier()
    normal = classifier.classify(sample_email(graph_id="same", subject="Bonjour"))
    spam = classifier.classify(
        sample_email(
            graph_id="same",
            subject="URGENT !!! Vous avez gagné",
            body_preview="Cliquez maintenant, offre exclusive gratuite !!!",
        )
    )

    assert spam["spam_score"] > normal["spam_score"]
