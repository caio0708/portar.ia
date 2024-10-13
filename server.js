const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors');

const app = express();
const PORT = 5000;

app.use(cors());
app.use(bodyParser.json());
app.use(express.static('public')); // Para servir arquivos estáticos como HTML e CSS

// Simulação de banco de dados em memória
const users = {};  // Altera de array para objeto para associar nomes de usuários

// Rota para login e registro
app.post('/', (req, res) => {
    const { username, action } = req.body;

    if (!username) {
        return res.status(400).json({ success: false, message: 'Nome de usuário não pode ser vazio.' });
    }

    // Verifica se a ação é "login"
    if (action === 'login') {
        if (users[username]) {
            return res.json({ success: true, message: 'Login bem-sucedido!' });
        } else {
            return res.json({ success: false, message: 'Usuário não encontrado!' });
        }
    }
    
    // Verifica se a ação é "register"
    if (action === 'register') {
        if (users[username]) {
            return res.json({ success: false, message: 'Usuário já existe.' });
        }
        // Adiciona o novo usuário ao objeto
        users[username] = { registered: true };
        return res.json({ success: true, message: 'Usuário registrado com sucesso.' });
    }

    return res.status(400).json({ success: false, message: 'Ação inválida.' });
});

// Rota para registro de rosto (simulada)
app.get('/face_registration', (req, res) => {
    res.sendFile(path.join(__dirname, 'templates', 'face_registration')); 
});

// Rota para verificação de rosto (simulada)
app.get('/verification', (req, res) => {
    res.sendFile(path.join(__dirname, 'templates', 'verification.html')); 
});

// Iniciar o servidor
app.listen(PORT, () => {
    console.log(`Servidor rodando em http://127.0.0.1:${PORT}`);
});
