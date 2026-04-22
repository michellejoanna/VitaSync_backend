from flask import Blueprint, request, jsonify
from datetime import datetime
from google import genai # NEW: Updated SDK
from models import User

chatbot_bp = Blueprint('chatbot_bp', __name__)

# Configure the new Gemini Client
client = genai.Client(api_key="AIzaSyBK-eufNypvZQp4DfH_m9CuNoKUAexwv2M")

@chatbot_bp.route('/ask_ai', methods=['POST'])
def ask_ai():
    data = request.get_json()
    user_id = data.get('user_id')
    user_message = data.get('message')
    
    if not user_message:
        return jsonify({'status': 'error', 'message': 'Message is empty.'}), 400

    user = User.query.get(user_id) if user_id else None
    
    # Base Context
    context = "You are VitaSync AI, a professional health, fitness, and diet coach. "
    
    if user:
        context += f"The user's name is {user.full_name}. "
        
        # Dynamic Nationality & Region
        if user.nationality and user.region:
            context += f"They live in {user.region}, {user.nationality}. You MUST prioritize regional dietary options, local foods, and culturally relevant fitness advice specific to this exact region. "
        
        # Dynamic Age Calculation
        # Dynamic Age Calculation
        if user.dob:
            try:
                dob_date = datetime.strptime(user.dob, "%d/%m/%Y")
                age = (datetime.utcnow() - dob_date).days // 365
                context += f"They are {age} years old. "
            except:
                pass
                
        if user.gender:
            context += f"Their gender is {user.gender}. " # NEW: AI knows the gender
                
        if user.height and user.weight:
            context += f"They weigh {user.weight}kg and are {user.height}cm tall. "
    
    context += "Keep responses concise, friendly, encouraging, and formatted well for a mobile app screen. Do not use markdown headers."

    try:
        full_prompt = f"{context}\n\nUser asks: {user_message}"
        
        # NEW: Updated generation method for the new SDK
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=full_prompt
        )
        
        return jsonify({'status': 'success', 'reply': response.text}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500