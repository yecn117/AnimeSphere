from flask import Flask, render_template, request, session, redirect, url_for, flash
from flask_socketio import join_room, leave_room, send, SocketIO
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.utils import secure_filename
import os
from sqlalchemy import func, or_
from werkzeug.security import check_password_hash, generate_password_hash



app = Flask (__name__)
app.config["SECRET_KEY"]= "jsjdjsjhd"
socketio = SocketIO(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///animesphere.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(200), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Chatroom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chatname = db.Column(db.String(255), unique=True, nullable=False)
    image = db.Column(db.String(255), nullable=True)


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user_name = db.Column(db.String(200), nullable=False)
    user = db.relationship('User', backref=db.backref('messages', lazy=True), foreign_keys=[user_id])

    chatroom_id = db.Column(db.Integer, db.ForeignKey('chatroom.id'), nullable=False)
    chatroom = db.relationship('Chatroom', backref=db.backref('messages', lazy=True), foreign_keys=[chatroom_id])
    




with app.app_context():
    db.create_all()
    


@app.route("/", methods=["POST", "GET"])
def home():
    if request.method == "POST":
        username = request.form.get("name")
        password = request.form.get("password")
        action = request.form.get("action")

        if not username or not password:
            return render_template("home.html", error="Bitte trage sowohl Benutzernamen als auch Passwort ein!", username=username)

        existing_user = User.query.filter_by(username=username).first()

        if action == "sign_in":
            if not existing_user:
                # Speichere den Benutzer in der Datenbank, wenn er nicht vorhanden ist
                hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
                new_user = User(username=username, password=hashed_password)
                db.session.add(new_user)
                db.session.commit()
                return render_template("home.html", message="Dein Benutzer wurde registriert!", username=username)
            else:
                return render_template("home.html", error="Dieser Benutzername existiert bereits!", username=username)

        elif action == "log_in":
            if existing_user and check_password_hash(existing_user.password, password):
                session["name"] = username
                return redirect(url_for("rooms"))
            else:
                return render_template("home.html", error="Benutzername oder Passwort ist falsch!", username=username)

    return render_template("home.html")



#rooms.html

@app.route("/rooms", methods=["GET"])

def rooms():
    if "name" in session:
        username = session["name"]
        welcome_message = f"Willkommen, {username}!"

        # Holen Sie alle Chatrooms
        chatrooms = Chatroom.query.all()

        # Überprüfen, ob eine Suchanfrage vorliegt
        search_query = request.args.get("search")
        if search_query:
            # Filtere nach Teilübereinstimmungen im Chatnamen
            chatrooms = Chatroom.query.filter(or_(Chatroom.chatname.ilike(f"%{search_query}%"))).all()

        # Überprüfen, ob Suchergebnisse vorhanden sind
        if not chatrooms:
            no_results_message = "Keine Chatrooms gefunden!"
        else:
            no_results_message = None

        return render_template("rooms.html", welcome_message=welcome_message, chatrooms=chatrooms, no_results_message=no_results_message)
    else:
        return redirect(url_for("home"))
    

@app.route('/AboutAnimeSphere')
def AboutAnimeSphere():
    return render_template('AboutAnimeSphere.html')

@app.route('/ContactUs')
def ContactUs():
    return render_template('ContactUs.html')


def normalize_chatname(chatname):
    return chatname.lower().strip()

@app.route("/create_room", methods=["POST"])
def create_room():

    if Chatroom.query.count() >= 100:
        flash("Es können nicht mehr als 100 Chatrooms erstellt werden.", "error")
        return redirect(url_for("rooms"))
    
    chatname = request.form.get("chatname")
    normalized_chatname = normalize_chatname(chatname)

    image = request.files.get("image")

    if not chatname or not image:
        flash("Bitte fülle alle Felder aus.", "error")
        return redirect(url_for("rooms"))

    if not allowed_file(image.filename):
        flash("Ungültige Dateiendung. Erlaubt sind: png, jpg, jpeg, gif", "error")
        return redirect(url_for("rooms"))

    # Überprüfe, ob ein Chatroom mit dem normalisierten Namen bereits existiert
    existing_chatroom = Chatroom.query.filter(func.lower(Chatroom.chatname) == normalized_chatname).first()

    if existing_chatroom:
        flash("Einen Chatroom zu diesem Anime existiert bereits!", "error")
        return redirect(url_for("rooms"))
    

    image_relative_path = os.path.join("img", "chatrooms", secure_filename(image.filename))
    image_relative_path = os.path.normpath(image_relative_path).replace("\\", "/")

    # Bild im statischen Verzeichnis speichern
    image_path = os.path.join("static", image_relative_path)
    image.save(image_path)

    new_chatroom = Chatroom(chatname=chatname, image=image_relative_path)
    db.session.add(new_chatroom)
    db.session.commit()

    flash("Chatroom erfolgreich erstellt!", "success")
    return redirect(url_for("rooms"))


@app.route("/chat/<chatroom_name>")
def chat(chatroom_name):
    chatroom = Chatroom.query.filter_by(chatname=chatroom_name).first()
    messages = Message.query.filter_by(chatroom=chatroom).all()

    if "name" in session:
        username = session["name"]
        return render_template("chat.html", chatroom_name=chatroom_name, user_name=username, messagess=messages)
    else:
        return redirect(url_for("home"))

@app.route("/chat/<chatroom_name>/save_message", methods=["POST"])
def save_message(chatroom_name):
    # Überprüfe, ob der Benutzer in der Sitzung (Session) vorhanden ist
    if "name" not in session:
        return redirect(url_for("home"))

    # Extrahiere Benutzername und Nachrichteninhalt aus dem Formular
    user_name = session["name"]
    content = request.form.get("content")

    # Überprüfe, ob die Nachricht nicht leer ist
    if not content:
        return redirect(url_for("chat", chatroom_name=chatroom_name))

    # Suche den Chatroom und den Benutzer in der Datenbank
    chatroom = Chatroom.query.filter_by(chatname=chatroom_name).first()
    user = User.query.filter_by(username=user_name).first()

    # Überprüfe, ob sowohl der Chatroom als auch der Benutzer gefunden wurden
    if chatroom and user:
        # Erstelle eine neue Nachricht und füge sie zur Datenbank hinzu
        new_message = Message(content=content, user=user, user_name=user.username, chatroom=chatroom)
        db.session.add(new_message)
        db.session.commit()

    # Leite den Benutzer zur Chatseite des entsprechenden Chatrooms weiter
    return redirect(url_for("chat", chatroom_name=chatroom_name))


            
    
    
if __name__ == "__main__":
    socketio.run(app, debug=True)