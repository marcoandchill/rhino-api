# Fichier modifié : send_question.py
import yagmail
import requests
import logging
from typing import Optional, Dict, Any
from config import EMAIL, PASSWORD
from utils import generate_question_id, load_conversations, save_conversations
from datetime import datetime

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configuration de l'API
API_BASE_URL = "http://localhost:8000/api"  # Modifiez selon votre configuration

class APIError(Exception):
    """Exception levée en cas d'erreur avec l'API"""
    pass

def get_challenge_from_api(user_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Récupère un challenge depuis l'API.
    
    Args:
        user_id: ID de l'utilisateur pour récupérer son challenge du jour
    
    Returns:
        Dict contenant les informations du challenge
    
    Raises:
        APIError: En cas d'erreur lors de la récupération
    """
    try:
        if not user_id:
            raise APIError("user_id doit être spécifié")
            
        # Récupération du challenge du jour pour un utilisateur
        url = f"{API_BASE_URL}/challenges/today"
        params = {"user_id": user_id}
        logger.info(f"Récupération du challenge du jour pour l'utilisateur {user_id}")
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if not data.get("success"):
            raise APIError(f"API Error: {data.get('message', 'Erreur inconnue')}")
        
        challenge_data = data.get("data", {})
        challenge = challenge_data.get("challenge")
        
        if not challenge:
            raise APIError("Aucun challenge disponible pour cet utilisateur")
            
        return {
            "question": challenge.get("question"),
            "matiere": challenge.get("matiere"),
            "challenge_id": challenge.get("challenge_id"),
            "ref": challenge.get("ref"),
            "user_subscriptions": challenge_data.get("user_subscriptions", [])
        }
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur de connexion à l'API: {e}")
        raise APIError(f"Impossible de se connecter à l'API: {e}")
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du challenge: {e}")
        raise APIError(f"Erreur inattendue: {e}")

def send_question_from_api(to: str, user_id: int = 1) -> bool:
    """
    Envoie une question à un étudiant en utilisant l'API
    
    Args:
        to: Email de l'étudiant
        user_id: ID de l'utilisateur
        
    Returns:
        bool: True si envoyé avec succès
    """
    try:
        # Récupérer les données du challenge depuis l'API
        challenge_data = get_challenge_from_api(user_id)
        if not challenge_data:
            logger.error("❌ Impossible de récupérer les données du challenge")
            return False
            
        # Extraire les données nécessaires
        question = challenge_data.get('question', '')
        matiere = challenge_data.get('matiere', 'Général')
        challenge_ref = challenge_data.get('ref', '')
        api_challenge_id = challenge_data.get('challenge_id')
        
        # Générer un ID local pour le suivi
        local_question_id = generate_question_id()
        
        # Préparer le corps du message
        html_body = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: Arial, sans-serif; background-color: #f9f9f9; padding: 20px;">
            <div style="max-width: 600px; margin: auto; background-color: #ffffff; padding: 30px; border-radius: 10px; box-shadow: 0 2px 6px rgba(0,0,0,0.1);">
            
            <h2 style="color: #333;">Bonjour,</h2>
            <p>Voici ta question du jour en <strong>{matiere}</strong> :</p>

            <h3 style="color: #2c3e50;">❓ Question</h3>
            <p>{question}</p>

            <h3 style="color: #2c3e50;">📚 Détails</h3>
            <ul>
                <li><strong>Matière :</strong> {matiere}</li>
                <li><strong>Référence :</strong> {challenge_ref}</li>
                <li><strong>ID de suivi :</strong> {local_question_id}</li>
                <li><strong>ID Challenge API :</strong> {api_challenge_id}</li>
            </ul>

            <p style="margin-top: 30px;">Bonne chance ! 🌸</p>

            <p style="margin-top: 40px;">Cordialement,<br><strong>Le Rhino 🦏</strong></p>

            <hr style="margin-top: 40px; border: none; border-top: 1px solid #eee;">
            <p style="font-size: 12px; color: #999; text-align: center;">
                Tu peux répondre directement à cet email pour soumettre ta réponse.
            </p>
            </div>
        </body>
        </html>
        """
        
        # Préparer le sujet
        subject = f"🧠 Question du jour - {local_question_id}"
        
        # Envoyer l'email avec threading
        success, message_id = send_threaded_email(
            to=to,
            subject=subject,
            body=html_body
        )
        
        if success:
            # Sauvegarder les données de la question
            question_data = {
                'student': to,
                'question': question,
                'matiere': matiere,
                'challenge_ref': challenge_ref,
                'api_challenge_id': api_challenge_id,
                'user_id': user_id,
                'sent_message_id': message_id,  # Sauvegarder le Message-ID
                'sent_at': datetime.now().isoformat()
            }
            
            # Essayer de sauvegarder en base de données d'abord
            from utils import save_question_to_db
            db_saved = save_question_to_db(
                question_id=local_question_id,
                student_email=to,
                question=question,
                matiere=matiere,
                challenge_ref=challenge_ref,
                api_challenge_id=api_challenge_id,
                user_id=user_id,
                sent_message_id=message_id
            )
            
            if not db_saved:
                # Fallback vers JSON si la base de données n'est pas disponible
                from utils import load_conversations, save_conversations
                conversations = load_conversations()
                conversations[local_question_id] = question_data
                save_conversations(conversations)
                
            logger.info(f"✅ Question envoyée avec succès à {to}")
            logger.info(f"Message-ID: {message_id}")
            return True
            
        else:
            logger.error(f"❌ Échec de l'envoi de la question à {to}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Erreur lors de l'envoi de la question: {e}")
        return False

def send_question(to: str, question: str):
    """
    Fonction legacy pour envoyer une question hardcodée.
    Conservée pour compatibilité.
    """
    logger.warning("Utilisation de la fonction legacy send_question. Utilisez send_question_from_api à la place.")
    
    question_id = generate_question_id()
    subject = f"🧠 Question du jour - {question_id}"
    body = f"""Bonjour,

Voici ta question du jour :

❓ {question}

[ID de la question : {question_id}]
"""
    try:
        yag = yagmail.SMTP(EMAIL, PASSWORD)
        yag.send(to=to, subject=subject, contents=body)
        logger.info(f"✅ Question legacy envoyée à {to} avec l'ID {question_id}")
    except Exception as e:
        logger.error(f"❌ Échec de l'envoi legacy : {e}")
        return

    conversations = load_conversations()
    conversations[question_id] = {
        "student": to,
        "question": question,
        "response": None,
        "evaluated": False
    }
    save_conversations(conversations)

# Fonctions utilitaires pour différents cas d'usage
def send_daily_challenge_to_user(email: str, user_id: int) -> bool:
    """Envoie le challenge du jour personnalisé à un utilisateur"""
    return send_question_from_api(email, user_id=user_id)

def send_subject_challenge(email: str, matiere: str) -> bool:
    """Envoie un challenge pour une matière spécifique"""
    return send_question_from_api(email, matiere=matiere)

def test_api_connection() -> bool:
    """Teste la connexion à l'API"""
    try:
        response = requests.get(f"{API_BASE_URL}/challenges/today", timeout=5)
        return response.status_code == 200
    except:
        return False

def send_threaded_email(to: str, subject: str, body: str, message_id: str = None, in_reply_to: str = None, references: str = None) -> tuple:
    """
    Envoie un email avec les headers de threading appropriés
    
    Args:
        to: Destinataire
        subject: Sujet de l'email
        body: Corps du message
        message_id: Message-ID à utiliser (si None, en génère un)
        in_reply_to: Message-ID auquel répondre
        references: Chaîne de Message-IDs pour le threading
        
    Returns:
        tuple: (success, message_id)
    """
    try:
        import yagmail
        from config import EMAIL, PASSWORD
        import uuid
        import time
        
        # Préparer les headers de threading
        headers = {}
        
        if in_reply_to:
            headers['In-Reply-To'] = in_reply_to
            
        if references:
            headers['References'] = references
            
        # Envoyer l'email avec les headers
        yag = yagmail.SMTP(EMAIL, PASSWORD)
        yag.send(
            to=to,
            subject=subject,
            contents=body,
            headers=headers
        )
        
        # Récupérer le Message-ID généré par yagmail
        # Note: yagmail ne nous donne pas accès au Message-ID généré
        # Nous devons donc le récupérer après l'envoi
        message_id = f"<{int(time.time())}-{str(uuid.uuid4())[:8]}@lerhinoo.gmail.com>"
        
        logger.info(f"✅ Email envoyé avec succès à {to}")
        logger.info(f"Message-ID: {message_id}")
        if in_reply_to:
            logger.info(f"In-Reply-To: {in_reply_to}")
        if references:
            logger.info(f"References: {references}")
            
        return True, message_id
        
    except Exception as e:
        logger.error(f"❌ Erreur envoi email: {e}")
        return False, None

def send_evaluation_response(to: str, question_id: str, evaluation: Dict, original_message_id: str, student_message_id: str) -> bool:
    """
    Envoie une réponse d'évaluation dans la chaîne de conversation
    
    Args:
        to: Email de l'étudiant
        question_id: ID de la question
        evaluation: Données d'évaluation
        original_message_id: Message-ID de la question originale
        student_message_id: Message-ID de la réponse de l'étudiant
        
    Returns:
        bool: True si envoyé avec succès
    """
    try:
        # Charger la conversation pour récupérer les infos
        from utils import load_conversations
        conversations = load_conversations()
        
        if question_id not in conversations:
            logger.error(f"Question {question_id} non trouvée dans les conversations")
            return False
            
        conversation = conversations[question_id]
        
        # Préparer le sujet et le corps
        matiere = conversation.get('matiere', 'Général')
        subject = f"🧠 Question du jour - {question_id}"
        
        # Extraire les données de l'évaluation
        api_data = evaluation.get('raw_api_response', {}).get('data', {})
        score = api_data.get('score', 'N/A')
        note = api_data.get('note', 'N/A')
        feedback = api_data.get('feedback', 'Aucun feedback disponible')
        points_forts = api_data.get('points_forts', [])
        points_ameliorer = api_data.get('points_ameliorer', [])
        suggestions = api_data.get('suggestions', [])
        reponse_modele = api_data.get('reponse_modele', '')
        
        # Corps du message
        body = f"""Bonjour,

Voici l'évaluation de votre réponse :

RÉSULTAT
Score : {score}/20
Note : {note}/20

FEEDBACK GÉNÉRAL
{feedback}

POINTS FORTS
{chr(10).join([f"• {point}" for point in points_forts]) if points_forts else "• Aucun point fort identifié"}

POINTS À AMÉLIORER
{chr(10).join([f"• {point}" for point in points_ameliorer]) if points_ameliorer else "• Aucun point d'amélioration spécifique"}

SUGGESTIONS
{chr(10).join([f"• {suggestion}" for suggestion in suggestions]) if suggestions else "• Aucune suggestion spécifique"}

{f"RÉPONSE MODÈLE{chr(10)}{reponse_modele}" if reponse_modele else ""}

Cordialement,
Le Rhino
"""
        
        # Construire la chaîne de References
        references = f"{original_message_id} {student_message_id}"
        
        # Envoyer l'email avec les headers de threading
        success, eval_message_id = send_threaded_email(
            to=to,
            subject=subject,
            body=body,
            in_reply_to=student_message_id,
            references=references
        )
        
        if success:
            # Mettre à jour la conversation avec le Message-ID de l'évaluation
            conversations[question_id]['evaluation_message_id'] = eval_message_id
            from utils import save_conversations
            save_conversations(conversations)
            
            logger.info(f"✅ Évaluation envoyée avec succès pour {question_id}")
            return True
        else:
            logger.error(f"❌ Échec de l'envoi de l'évaluation pour {question_id}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Erreur lors de l'envoi de l'évaluation: {e}")
        return False

if __name__ == "__main__":
    # Tests et exemples d'utilisation
    
    # Test de connexion API
    if test_api_connection():
        logger.info("✅ Connexion API OK")
    else:
        logger.error("❌ Connexion API échouée")
    
    # Exemples d'utilisation :
    
    # 1. Envoyer le challenge du jour pour un utilisateur spécifique
    # success = send_daily_challenge_to_user("mathis.beaufour71@gmail.com", user_id=1)
    
    # 2. Envoyer un challenge pour une matière spécifique
    # success = send_subject_challenge("mathis.beaufour71@gmail.com", "informatique")
    
    # 3. Utilisation générale
    success = send_question_from_api("mathis.beaufour71@gmail.com", user_id=1)
    
    if success:
        logger.info("🎉 Challenge envoyé avec succès!")
    else:
        logger.error("💥 Échec de l'envoi du challenge")

# send_daily_challenge_to_user("student@example.com", user_id=1) 