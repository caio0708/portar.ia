from flask import Flask, render_template, request, jsonify
import os
import sqlite3
import cv2
import numpy as np
import paho.mqtt.client as mqtt
import base64
from flask_login import LoginManager, UserMixin, current_user, login_user, login_required

# Caminhos para o banco de dados e diretórios de armazenamento
DB_PATH = "face_recognition.db"
FACES_DIR = "faces/"
MODEL_PATH = "face_recognizer.yml"
FACE_SIZE = (200, 200)  # Dimensão padrão para as imagens de rosto
NUM_SAMPLES = 15  # Número de amostras de rosto a serem capturadas por usuário

MQTT_BROKER = "broker.hivemq.com"  # Endereço do broker MQTT
MQTT_PORT = 1883  # Porta do broker MQTT
MQTT_TOPIC = "acesso/usuario"  # Tópico MQTT

# Configurar o cliente MQTT
client = mqtt.Client()
client.connect(MQTT_BROKER, MQTT_PORT, 60)

# Inicialização do classificador de rostos (detecção de rostos) e do reconhecedor facial
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
recognizer = cv2.face.LBPHFaceRecognizer_create()  # Algoritmo LBPH para reconhecimento facial

# Aplicativo Flask
app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui'  # Necessário para sessões
login_manager = LoginManager()
login_manager.init_app(app)

# Classe de usuário
class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

# Carregador de usuários
@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, username FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    if user:
        return User(user[0], user[1])
    return None

# Funções de banco de dados e reconhecimento facial
def initialize_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS faces (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, face_path TEXT, FOREIGN KEY (user_id) REFERENCES users(id))''')
    conn.commit()
    conn.close()

# Adiciona, verifica a existência do usuário, etc.
def add_user(username):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO users (username) VALUES (?)', (username,))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def user_exists(username):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    return user is not None

def add_face(user_id, face_path):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO faces (user_id, face_path) VALUES (?, ?)', (user_id, face_path))
    conn.commit()
    conn.close()

def get_user_id(label):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM users WHERE id = ?', (label,))
    user_id = cursor.fetchone()
    conn.close()
    return user_id[0] if user_id else None

def get_faces(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT face_path FROM faces WHERE user_id = ?', (user_id,))
    faces = cursor.fetchall()
    conn.close()
    return [face[0] for face in faces]

def get_user_by_username(username):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    return user[0] if user else None

def train_face_recognizer():
    face_samples = []
    labels = []
    label_map = {}
    label_id = 0
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, username FROM users') 
    users = cursor.fetchall()

    for user_id, username in users:
        user_faces_dir = os.path.join(FACES_DIR, username)
        if not os.path.isdir(user_faces_dir):
            continue

        label_map[label_id] = username
        label_id += 1  
        faces_paths = get_faces(user_id)
        for face_path in faces_paths:
            image = cv2.imread(face_path, cv2.IMREAD_GRAYSCALE)
            if image is not None:
                face = cv2.resize(image, FACE_SIZE)
                face = cv2.equalizeHist(face)
                face_samples.append(face)
                labels.append(user_id)

    if face_samples:
        recognizer.train(face_samples, np.array(labels))
        recognizer.save(MODEL_PATH)

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/face_registration.html')
def face_registration():
    return render_template('face_registration.html')

@app.route('/verification.html')
def verification():
    return render_template('verification.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.json.get('username')
    if username:
        if user_exists(username):
            user_id = get_user_by_username(username)
            user = User(user_id, username)
            login_user(user)  # Loga o usuário
            return jsonify(success=True, message='Login bem-sucedido!'), 200
        else:
            return jsonify(success=False, message='Usuário não encontrado!'), 404
    else:
        return jsonify(success=False, message='Nome de usuário não fornecido!'), 400

@app.route('/register_user', methods=['POST'])
def register_user():
    username = request.json.get('username')
    if username:
        if user_exists(username):
            return jsonify({'status': 'error', 'message': 'Usuário já existe!'}), 400
        user_id = add_user(username)
        if user_id:
            user_faces_dir = os.path.join(FACES_DIR, username)
            os.makedirs(user_faces_dir, exist_ok=True)
            return jsonify({'status': 'success', 'message': 'Usuário registrado com sucesso!'}), 201
        else:
            return jsonify({'status': 'error', 'message': 'Erro ao registrar usuário.'}), 500
    else:
        return jsonify({'status': 'error', 'message': 'Digite um nome de usuário!'}), 400

num_samples = 0  # Inicializando a contagem de amostras

@app.route('/register_face', methods=['POST'])
@login_required  # Protegendo a rota para que apenas usuários logados possam acessar
def register_face():
    global num_samples
    data = request.json
    image_data = data.get('image')

    if image_data:
        header, encoded = image_data.split(',', 1)
        face_data = base64.b64decode(encoded)
        np_img = np.frombuffer(face_data, np.uint8)
        frame = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

        if frame is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.3, 5)

            for (x, y, w, h) in faces:
                face = gray[y:y+h, x:x+w]
                face = cv2.resize(face, FACE_SIZE)
                face = cv2.equalizeHist(face)

                user_faces_dir = os.path.join(FACES_DIR, current_user.username)  # Usando o nome de usuário
                os.makedirs(user_faces_dir, exist_ok=True)

                face_path = os.path.join(user_faces_dir, f"sample_{num_samples}.jpg")
                cv2.imwrite(face_path, face)
                add_face(current_user.id, face_path)  # Adiciona o rosto ao banco de dados
                num_samples += 1

                if num_samples >= NUM_SAMPLES:
                    train_face_recognizer()
                    return jsonify({"status": "success", "message": "Cadastro de rosto concluído!"}), 200

            return jsonify({"status": "success", "message": f"Amostra {num_samples + 1} capturada!"}), 200

    return jsonify({"status": "error", "message": "Erro ao capturar a imagem."}), 400

@app.route('/verify_face', methods=['POST'])
def verify_face():
    data = request.json
    image_data = data.get('image')

    if image_data:
        header, encoded = image_data.split(',', 1)
        face_data = base64.b64decode(encoded)
        np_img = np.frombuffer(face_data, np.uint8)
        frame = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

        if frame is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.3, 5)

            for (x, y, w, h) in faces:
                face = gray[y:y+h, x:x+w]
                face = cv2.resize(face, FACE_SIZE)
                face = cv2.equalizeHist(face)

                label, confidence = recognizer.predict(face)
                username = get_user_id(label)

                if confidence < 100:  # Ajuste o limiar de confiança conforme necessário
                    # Envia a mensagem via MQTT
                    client.publish(MQTT_TOPIC, f"Usuário {username} reconhecido!")
                    return jsonify({"status": "success", "message": f"Usuário {username} reconhecido!"}), 200

            return jsonify({"status": "error", "message": "Nenhum rosto reconhecido."}), 404

    return jsonify({"status": "error", "message": "Erro ao capturar a imagem."}), 400

if __name__ == '__main__':
    initialize_database()  # Inicializa o banco de dados
    train_face_recognizer()  # Treina se houver rostos existentes
    app.run(debug=True)
