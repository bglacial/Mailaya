from __future__ import annotations

from datetime import datetime, timedelta, timezone


DEMO_MESSAGES = [
    ("OVHcloud", "Votre nom de domaine arrive à expiration dans 15 jours", "Le renouvellement de votre domaine doit être effectué avant le 12 octobre afin d'éviter une interruption.", "support@ovhcloud.com"),
    ("Notion", "Les nouveautés de septembre, en quelques minutes", "Découvrez les nouvelles vues, modèles et intégrations de Notion. Aucun suivi n'est nécessaire.", "team@mail.notion.so"),
    ("Nicolas Perrin", "Disponibilités pour un échange sur une formation IA", "Bonjour, pouvez-vous me confirmer un créneau mardi ou jeudi avant demain soir ?", "nicolas.perrin@example.com"),
    ("Chronopost", "Votre colis sera livré demain entre 10 h et 12 h", "Votre colis est en route. Suivez sa livraison depuis votre espace.", "ne-pas-repondre@chronopost.fr"),
    ("Lucie — Le Tank", "Petit rappel : rencontre créateurs jeudi à 18 h 30", "Pouvez-vous confirmer votre présence avant mercredi midi ?", "lucie@letank.fr"),
    ("Adobe", "Votre facture de septembre est disponible", "La facture de votre abonnement Creative Cloud est disponible dans votre compte.", "mail@adobe.com"),
    ("LinkedIn", "Sarah et 4 autres personnes ont réagi à votre publication", "Votre publication suscite des réactions. Consultez les nouvelles interactions.", "notifications-noreply@linkedin.com"),
    ("WeTransfer", "Maison Alba vous a envoyé 8 fichiers", "Les fichiers seront disponibles pendant 7 jours. Téléchargez-les avant leur expiration.", "noreply@wetransfer.com"),
    ("Orange", "Votre facture internet de 39,99 € est disponible", "Votre facture est disponible. Le prélèvement aura lieu le 28 septembre.", "facture@orange.fr"),
    ("Service achats", "Validation du devis mobilier avant vendredi", "Merci de valider ou refuser le devis joint avant vendredi 12 h pour maintenir la livraison.", "achats@example.com"),
    ("Promo Express", "URGENT !!! Vous avez gagné un iPhone", "Cliquez maintenant pour réclamer votre cadeau. Offre exclusive limitée.", "winner@promo-example.biz"),
    ("GitHub", "Security alert: vulnerable dependency detected", "A high severity vulnerability was detected. Review the alert and update the dependency.", "noreply@github.com"),
]

# Scénarios fictifs variés, répétés avec une référence unique pour simuler une
# boîte de réception de 500 messages sans données personnelles réelles.
_DEMO_SCENARIOS = [
    ("Camille Martin", "Validation du projet Atlas", "Pouvez-vous valider le compte rendu avant vendredi ?", "camille@example.com"),
    ("Banque Exemple", "Votre relevé mensuel est disponible", "Le relevé de votre compte est disponible dans votre espace sécurisé.", "releves@banque.example"),
    ("Support Hébergeur", "Incident sur votre espace web", "Un incident affecte votre service. Notre équipe travaille à sa résolution.", "support@hebergeur.example"),
    ("Librairie du Centre", "Votre commande est prête", "Votre commande peut être retirée en magasin dès aujourd'hui.", "commandes@librairie.example"),
    ("Association Créative", "Invitation à la rencontre de jeudi", "Confirmez votre présence à la rencontre avant mercredi.", "evenements@association.example"),
    ("Réseau Pro", "Une personne a réagi à votre publication", "Découvrez les nouvelles interactions sur votre publication.", "notifications@reseau.example"),
    ("Maman", "Dîner dimanche ?", "On se retrouve en famille dimanche pour dîner ? Réponds-moi quand tu peux.", "maman@example.com"),
    ("Marché Local", "Les nouveautés de la semaine", "Découvrez notre newsletter et les produits de saison.", "lettre@marche.example"),
    ("Service comptable", "Facture à régler", "Merci de vérifier la facture et d'effectuer le paiement avant la date indiquée.", "compta@example.com"),
    ("Équipe sécurité", "Alerte de sécurité sur votre compte", "Une connexion inhabituelle a été détectée. Vérifiez votre activité rapidement.", "securite@example.com"),
    ("Transport Colis", "Votre colis est en livraison", "La livraison de votre commande est prévue demain matin.", "suivi@transport.example"),
    ("Centre de formation", "Programme de la formation IA", "La formation commence mardi. Retrouvez le programme et les horaires.", "formation@centre.example"),
    ("Sophie Durand", "Point sur le dossier client", "Peux-tu relire la proposition et me répondre avant demain ?", "sophie@example.com"),
    ("Assurance Exemple", "Avis de remboursement", "Votre remboursement a été validé et sera versé prochainement.", "services@assurance.example"),
    ("Équipe produit", "Compte rendu de réunion", "Voici les décisions prises en réunion et les prochaines étapes du projet.", "produit@example.com"),
    ("Festival des Idées", "Votre invitation au festival", "Les conférences commencent samedi. Votre inscription est confirmée.", "bonjour@festival.example"),
    ("Boutique Exemple", "Offre exclusive du week-end", "Profitez de notre promotion sur une sélection de produits.", "offres@boutique.example"),
    ("Support Logiciel", "Votre demande d'assistance est résolue", "Le support a corrigé l'incident. Merci de confirmer que tout fonctionne.", "aide@logiciel.example"),
    ("Julien Bernard", "Des nouvelles pour samedi", "Salut, es-tu disponible pour un déjeuner samedi ?", "julien@example.com"),
    ("Fournisseur Bureau", "Devis pour votre commande", "Le devis demandé est disponible. Merci de le valider avant vendredi.", "devis@fournisseur.example"),
    ("Communauté Photo", "Votre publication a été commentée", "Un membre a laissé un commentaire sur votre publication.", "communaute@photo.example"),
    ("Service RH", "Rappel de votre entretien", "Votre entretien est prévu demain à 14 h. Pouvez-vous confirmer ?", "rh@example.com"),
    ("Énergie Exemple", "Votre facture d'électricité", "La facture mensuelle est disponible. Le prélèvement est prévu le 5.", "factures@energie.example"),
    ("Promo Flash", "Vous avez gagné un cadeau !!!", "Cliquez maintenant pour obtenir votre cadeau gratuit. Offre exclusive !", "gagnant@promo.example"),
]

for _index in range(500 - len(DEMO_MESSAGES)):
    _sender, _subject, _body, _address = _DEMO_SCENARIOS[_index % len(_DEMO_SCENARIOS)]
    _reference = _index + 1
    DEMO_MESSAGES.append(
        (_sender, f"{_subject} · réf. {_reference:03d}", f"{_body} Référence fictive {_reference:03d}.", _address)
    )


def demo_messages(since: str, limit: int) -> list[dict]:
    base = datetime.now(timezone.utc)
    results = []
    for index, (sender, subject, body, address) in enumerate(DEMO_MESSAGES[:limit]):
        received = base - timedelta(hours=index * 7 + 1)
        results.append(
            {
                "graph_id": f"demo-{index + 1}",
                "sender_name": sender,
                "sender_address": address,
                "subject": subject,
                "body_preview": body,
                "received_at": received.isoformat(),
            }
        )
    return results
