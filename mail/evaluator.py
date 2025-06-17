#!/usr/bin/env python3
"""
Simple response evaluation functionality
"""

import logging
import requests
from typing import Dict, Optional
import re
import yagmail
from config import EMAIL, PASSWORD
import json

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def evaluate_response_simple(question: str, response: str, matiere: str, user_id: int = 1) -> Dict:
    """
    Évaluation d'une réponse via l'API d'évaluation
    
    Args:
        question: La question posée
        response: La réponse de l'étudiant
        matiere: La matière concernée
    
    Returns:
        Dict contenant la réponse brute de l'API
        
    Raises:
        Exception: Si l'API d'évaluation n'est pas disponible ou retourne une erreur
    """
    # Préparer les données pour l'API (format attendu par l'API)
    api_data = {
        'question': question,
        'reponse_etudiant': response,  # Changé de 'response' à 'reponse_etudiant'
        'matiere': matiere
    }
    
    # Appel à l'API d'évaluation avec user_id requis
    logger.info(f"Appel API d'évaluation pour la matière: {matiere} (user_id: {user_id})")
    api_response = requests.post(
        f'http://localhost:8000/api/evaluation/response?user_id={user_id}',  # Utilise le user_id de l'étudiant
        json=api_data,
        headers={'Content-Type': 'application/json'},
        timeout=30
    )
    
    if api_response.status_code == 200:
        api_result = api_response.json()
        logger.info(f"✅ Évaluation réussie - API Response reçue")
        
        # Retourner la réponse brute de l'API pour l'instant
        return {
            'raw_api_response': api_result,
            'api_status': 'success',
            'status_code': api_response.status_code
        }
    else:
        logger.error(f"❌ Erreur API: {api_response.status_code} - {api_response.text}")
        raise Exception(f"Erreur API d'évaluation: {api_response.status_code}")

def clean_student_response(response: str) -> str:
    """
    Nettoie la réponse de l'étudiant en enlevant les parties non pertinentes
    
    Args:
        response: Réponse brute de l'étudiant
        
    Returns:
        str: Réponse nettoyée
    """
    if not response:
        return ""
        
    # Convertir en string si ce n'est pas déjà le cas
    response = str(response)
    
    # Enlever les parties de l'email original
    lines = response.split('\n')
    cleaned_lines = []
    skip_line = False
    
    for line in lines:
        # Ignorer les lignes de citation d'email
        if any(pattern in line.lower() for pattern in [
            'wrote:', 'écrit :', 'de :', 'from:', 'envoyé :', 'sent:',
            'objet :', 'subject:', 'date :', 'date:', 'à :', 'to:',
            'cc :', 'cc:', 'bcc :', 'bcc:', 'répondre à :', 'reply-to:'
        ]):
            skip_line = True
            continue
            
        # Ignorer les lignes de séparation d'email
        if line.strip().startswith('---') or line.strip().startswith('==='):
            skip_line = True
            continue
            
        # Ignorer les lignes de formatage d'email
        if line.strip().startswith('>'):
            skip_line = True
            continue
            
        # Réinitialiser skip_line si on trouve une ligne vide
        if not line.strip():
            skip_line = False
            
        # Ajouter la ligne si on ne doit pas la sauter
        if not skip_line:
            cleaned_lines.append(line)
    
    # Rejoindre les lignes et nettoyer
    cleaned = '\n'.join(cleaned_lines)
    
    # Enlever les espaces multiples
    cleaned = ' '.join(cleaned.split())
    
    # Enlever les retours à la ligne multiples
    cleaned = re.sub(r'\n\s*\n', '\n', cleaned)
    
    # Enlever les espaces au début et à la fin
    cleaned = cleaned.strip()
    
    return cleaned

# Les fonctions d'évaluation locales ont été supprimées car l'évaluation
# se fait maintenant via l'API /api/evaluation/response

def display_evaluation(evaluation: Dict, question: str, response: str):
    """Affiche l'évaluation de manière formatée"""
    import json
    
    # Nettoyer la réponse pour l'affichage
    clean_response = clean_student_response(response)
    
    print("\n" + "🤖" * 30)
    print("RÉPONSE BRUTE DE L'API D'ÉVALUATION")
    print("🤖" * 30)
    
    print(f"📝 Question: {question[:100]}...")
    print(f"📄 Réponse nettoyée: {clean_response[:100]}...")
    print(f"📊 Status Code: {evaluation.get('status_code', 'N/A')}")
    print(f"🔗 API Status: {evaluation.get('api_status', 'N/A')}")
    
    print("\n🤖 Réponse complète de l'API:")
    print(json.dumps(evaluation.get('raw_api_response', {}), indent=2, ensure_ascii=False))
    
    print("\n" + "🤖" * 30)

def evaluate_and_display(question: str, response: str, matiere: str, user_id: int = 1) -> Dict:
    """Évalue et affiche une réponse"""
    evaluation = evaluate_response_simple(question, response, matiere, user_id)
    display_evaluation(evaluation, question, response)
    return evaluation

def send_feedback_email(to_email: str, evaluation: Dict, question: str, response: str, student_name: str = None, original_email: Dict = None) -> bool:
    """
    Envoie un email de feedback avec l'évaluation à l'étudiant en réponse à son email
    
    Args:
        to_email: Adresse email de l'étudiant
        evaluation: Dictionnaire contenant l'évaluation (ou réponse brute de l'API)
        question: Question originale
        response: Réponse de l'étudiant
        student_name: Nom de l'étudiant (optionnel)
        original_email: Dict contenant les infos de l'email original pour créer une réponse
    
    Returns:
        bool: True si envoyé avec succès
    """
    try:
        logger = logging.getLogger(__name__)

        student_greeting = f"Bonjour {student_name}" if student_name else "Bonjour"

        # Extraire les données d’évaluation
        api_data = evaluation.get('raw_api_response', {}).get('data', {})
        score = api_data.get('score', 'N/A')
        note = api_data.get('note', 'N/A')
        feedback = api_data.get('feedback', 'Aucun feedback disponible')
        points_forts = api_data.get('points_forts', [])
        points_ameliorer = api_data.get('points_ameliorer', [])
        suggestions = api_data.get('suggestions', [])
        reponse_modele = api_data.get('reponse_modele', '')

        # Traitement de l'ID de question et de la matière pour l’objet
        question_id = None
        matiere = "Général"
        if original_email:
            matiere = original_email.get('matiere', 'Général')
            if original_email.get('question_id'):
                question_id = original_email['question_id']
            elif original_email.get('subject'):
                match = re.search(r'(IDQ-\d{14}-[a-f0-9]{6})', str(original_email['subject']))
                if match:
                    question_id = match.group(1)

        subject = f"🧠 Question du jour - {question_id}" if question_id else "🧠 Question du jour"

        # Génération du contenu HTML
        score_percent = int((int(note) / 20) * 100) if note != 'N/A' else 0

        body_html = f"""
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: Arial, sans-serif; background-color: #f9f9f9; padding: 20px;">
            <div style="max-width: 600px; margin: auto; background-color: #ffffff; padding: 30px; border-radius: 10px; box-shadow: 0 2px 6px rgba(0,0,0,0.1);">
            
            <h2 style="color: #333;">{student_greeting},</h2>
            <p>Voici l'évaluation de votre réponse à la question du jour :</p>

            <h3 style="color: #2c3e50;">📝 Question</h3>
            <p>{question}</p>

            <h3 style="color: #2c3e50;">📊 Résultat</h3>
            <div style="background-color: #f0f8ff; padding: 10px 15px; border-radius: 8px; margin-bottom: 10px;">
                <p><strong>Note :</strong> {note}/20</p>
                <div style="background-color: #eee; border-radius: 8px; height: 10px; margin-top: 10px;">
                <div style="width: {score_percent}%; background-color: #4CAF50; height: 10px; border-radius: 8px;"></div>
                </div>
                <p style="font-size: 12px; color: #666;">Progression : {score}/20</p>
            </div>

            <h3 style="color: #2c3e50;">🧾 Feedback général</h3>
            <p>{feedback}</p>

            <h3 style="color: #2c3e50;">✅ Points forts</h3>
            <ul>
                {''.join(f"<li>{point}</li>" for point in points_forts) if points_forts else "<li>Aucun point fort identifié</li>"}
            </ul>

            <h3 style="color: #2c3e50;">⚠️ Points à améliorer</h3>
            <ul>
                {''.join(f"<li>{point}</li>" for point in points_ameliorer) if points_ameliorer else "<li>Aucun point d'amélioration spécifique</li>"}
            </ul>

            <h3 style="color: #2c3e50;">💡 Suggestions</h3>
            <ul>
                {''.join(f"<li>{s}</li>" for s in suggestions) if suggestions else "<li>Aucune suggestion spécifique</li>"}
            </ul>

            {f"""
            <h3 style='color: #2c3e50;'>📚 Réponse Modèle</h3>
            <p style='background-color: #f0f0f0; padding: 10px; border-radius: 5px;'>{reponse_modele}</p>
            """ if reponse_modele else ""}

            <p style="margin-top: 30px;">Cordialement,<br><strong>Le Rhino 🦏</strong></p>
            <hr style="margin-top: 40px; border: none; border-top: 1px solid #eee;">
            <p style="font-size: 12px; color: #999; text-align: center;">
                Ce message a été généré automatiquement.
            </p>
            </div>
        </body>
        </html>
        """

        # Envoi de l’email
        logger.info(f"Envoi du feedback à {to_email}")
        logger.info(f"Sujet: {subject}")
        yag = yagmail.SMTP(EMAIL, PASSWORD)
        yag.send(to=to_email, subject=subject, contents=body_html)
        logger.info(f"✅ Feedback envoyé avec succès à {to_email}")
        return True
    except Exception as e:
        logger.error(f"❌ Erreur envoi feedback: {e}")
        return False

# Les fonctions de formatage de l'ancien système d'évaluation ont été supprimées
# car nous utilisons maintenant la réponse brute de l'API d'évaluation

def send_apology_email(to_email: str, question: str, response: str, student_name: str = None, original_email: Dict = None, error_details: str = "") -> bool:
    """
    Envoie un email d'excuses lorsque l'évaluation automatique n'est pas disponible
    
    Args:
        to_email: Adresse email de l'étudiant
        question: Question originale
        response: Réponse de l'étudiant
        student_name: Nom de l'étudiant (optionnel)
        original_email: Dict contenant les infos de l'email original pour créer une réponse
        error_details: Détails de l'erreur (optionnel)
    
    Returns:
        bool: True si envoyé avec succès
    """
    try:
        logger = logging.getLogger(__name__)

        student_greeting = f"Bonjour {student_name}" if student_name else "Bonjour"

        # Sujet de l'email
        if original_email and original_email.get('subject'):
            original_subject = original_email['subject']
            clean_subject = original_subject
            while clean_subject.startswith('Re: ') or clean_subject.startswith('RE: '):
                clean_subject = clean_subject[4:]
            subject = f"Re: {clean_subject} - ⚠️ Problème technique temporaire"
        else:
            subject = "⚠️ Problème technique temporaire - Évaluation différée"

        # Corps HTML
        body_html = f"""
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: Arial, sans-serif; background-color: #f9f9f9; padding: 20px;">
            <div style="max-width: 600px; margin: auto; background-color: #ffffff; padding: 30px; border-radius: 10px; box-shadow: 0 2px 6px rgba(0,0,0,0.1);">
            
            <h2 style="color: #333;">{student_greeting},</h2>
            <p>Nous vous remercions pour votre réponse à la question du jour.</p>

            <h3 style="color: #2c3e50;">📝 Question</h3>
            <p>{question}</p>

            <h3 style="color: #2c3e50;">📄 Votre réponse</h3>
            <p style="background-color: #f0f0f0; padding: 10px; border-radius: 5px;">
                {response[:200]}{'...' if len(response) > 200 else ''}
            </p>

            <h3 style="color: #d35400;">⚠️ Problème technique temporaire</h3>
            <p>Nous rencontrons actuellement un problème technique avec notre système d'évaluation automatique.</p>

            <h3 style="color: #2c3e50;">🔧 Solution en cours</h3>
            <ul>
                <li>Notre équipe technique travaille activement à résoudre ce problème.</li>
                <li>Votre réponse a bien été reçue et enregistrée.</li>
                <li>L'évaluation sera effectuée dès que possible.</li>
            </ul>

            <h3 style="color: #2c3e50;">📧 Prochaines étapes</h3>
            <p>Vous recevrez votre évaluation détaillée par email dès que notre système sera rétabli (généralement sous 24h).</p>

            <h3 style="color: #2c3e50;">🙏 Sincères excuses</h3>
            <p>Nous vous prions de nous excuser pour ce désagrément temporaire et vous remercions de votre patience.</p>

            <p style="margin-top: 30px;">Cordialement,<br><strong>L'équipe pédagogique 🎓</strong></p>

            <hr style="margin-top: 40px; border: none; border-top: 1px solid #eee;">
            <p style="font-size: 12px; color: #999; text-align: center;">
                Ce message a été généré automatiquement.
            </p>
            </div>
        </body>
        </html>
        """

        # Envoi du mail
        yag = yagmail.SMTP(EMAIL, PASSWORD)
        logger.info(f"Envoi d'email d'excuses à {to_email}")

        headers = {}
        if original_email:
            original_message_id = original_email.get('message_id')
            if original_message_id:
                headers['In-Reply-To'] = original_message_id
                headers['References'] = original_message_id
                logger.info(f"Envoi en réponse au message ID: {original_message_id}")

        if headers:
            yag.send(to=to_email, subject=subject, contents=body_html, headers=headers)
        else:
            yag.send(to=to_email, subject=subject, contents=body_html)

        logger.info(f"✅ Email d'excuses envoyé avec succès à {to_email}")
        return True

    except Exception as e:
        logger.error(f"❌ Erreur envoi email d'excuses: {e}")
        return False

def evaluate_display_and_send_feedback(question: str, response: str, matiere: str, 
                                      student_email: str, student_name: str = None, original_email: Dict = None, user_id: int = 1) -> tuple:
    """
    Évalue une réponse, l'affiche et envoie le feedback par email
    
    Returns:
        tuple: (evaluation_dict, feedback_sent_success)
    """
    try:
        # Évaluer et afficher
        evaluation = evaluate_and_display(question, response, matiere, user_id)
        
        # S'assurer que original_email contient la matière
        if original_email is None:
            original_email = {}
        if 'matiere' not in original_email:
            original_email['matiere'] = matiere
        
        # Envoyer le feedback
        feedback_sent = send_feedback_email(student_email, evaluation, question, response, student_name, original_email)
        
        return evaluation, feedback_sent
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de l'évaluation: {e}")
        
        # Envoyer un email d'excuses en français
        apology_sent = send_apology_email(student_email, question, response, student_name, original_email, str(e))
        
        return None, apology_sent 