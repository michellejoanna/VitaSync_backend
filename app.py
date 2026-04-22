from flask import Flask, send_from_directory
from models import db
from routes.signup import signup_bp
from routes.login import login_bp
from routes.profile import profile_bp
from routes.chatbot import chatbot_bp
from routes.home import home_bp
from routes.scanner import scanner_bp 
from routes.goal_engine import goal_bp 
from routes.blueprint_data import blueprint_data_bp # NEW IMPORT

app = Flask(__name__)

# Connect to XAMPP MySQL
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:12345@localhost/vitasync'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()

# Register the separated route files
app.register_blueprint(signup_bp)
app.register_blueprint(login_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(chatbot_bp)
app.register_blueprint(home_bp)
app.register_blueprint(scanner_bp) 
app.register_blueprint(goal_bp)
app.register_blueprint(blueprint_data_bp) # REGISTER NEW FILE

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory('uploads', filename)

if __name__ == '__main__':
    # Run on 0.0.0.0 so your Android phone can access it via IPv4
    app.run(host='0.0.0.0', port=5000, debug=True)