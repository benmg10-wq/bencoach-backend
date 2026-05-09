const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
require('dotenv').config();

const connectDB = require('./utils/db');

const app = express();

// ============================================
// MIDDLEWARES (ORDER IS CRITICAL!)
// ============================================

// 1. Security
app.use(helmet());

// 2. CORS - before routes
app.use(cors({
  origin: [
    'http://localhost:5500',
    'http://localhost:5173',
    'https://ben-coach.com',
    'https://www.ben-coach.com'
  ],
  credentials: true
}));

// 3. Body parser - BEFORE routes that need req.body
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// 4. Logging
app.use(morgan('dev'));

// ============================================
// DATABASE CONNECTION
// ============================================
connectDB();

// ============================================
// ROUTES (AFTER body parser!)
// ============================================
app.use('/api/avis', require('./routes/avis'));
app.use('/api/auth', require('./routes/auth'));
app.use('/api/users', require('./routes/users'));
app.use('/api/programs', require('./routes/programs'));
app.use('/api/dashboard', require('./routes/dashboard'));
app.use('/api/nutrition', require('./routes/nutrition'));
app.use('/api/payments', require('./routes/payments'));

// ============================================
// ROOT ROUTE
// ============================================
app.get('/', (req, res) => {
  res.json({
    message: 'API BenCoach opérationnelle ✅',
    timestamp: new Date().toISOString(),
    endpoints: [
      '/api/avis',
      '/api/auth',
      '/api/users',
      '/api/programs',
      '/api/dashboard',
      '/api/nutrition',
      '/api/payments'
    ]
  });
});

// ============================================
// ERROR HANDLING
// ============================================
app.use((req, res) => {
  res.status(404).json({ message: 'Route non trouvée ❌' });
});

app.use((err, req, res, next) => {
  console.error('❌ Erreur:', err.stack);
  res.status(500).json({
    message: 'Erreur serveur',
    error: process.env.NODE_ENV === 'development' ? err.message : undefined
  });
});

// ============================================
// START SERVER
// ============================================
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`🚀 Serveur BenCoach sur port ${PORT}`);
  console.log(`📡 API disponible sur http://localhost:${PORT}`);
});
