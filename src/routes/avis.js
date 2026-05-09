const express = require('express');
const router = express.Router();
const Avis = require('../models/Avis');

console.log('✅ Route /api/avis chargée');

// GET /api/avis - Récupérer tous les avis
router.get('/', async (req, res) => {
    console.log('📥 GET /api/avis appelé');
    try {
        const avis = await Avis.find().sort({ createdAt: -1 });
        console.log('📤 Avis trouvés:', avis.length);
        res.status(200).json(avis);
    } catch (error) {
        console.error('❌ Erreur GET /api/avis:', error);
        res.status(500).json({
            message: 'Erreur lors de la récupération des avis',
            error: error.message
        });
    }
});

// POST /api/avis - Créer un nouvel avis
router.post('/', async (req, res) => {
    console.log('📥 POST /api/avis appelé');
    console.log('Body reçu:', req.body);

    try {
        const { nom, pack, note, resultat, texte } = req.body;

        // Validation
        if (!nom || !pack || !note || !texte) {
            console.log('❌ Validation échouée - champs manquants');
            return res.status(400).json({
                message: 'Champs obligatoires manquants: nom, pack, note, texte'
            });
        }

        const newAvis = new Avis({
            nom: nom.trim(),
            pack,
            note: parseInt(note),
            resultat: resultat ? resultat.trim() : '',
            texte: texte.trim()
        });

        const savedAvis = await newAvis.save();
        console.log('✅ Avis sauvegardé:', savedAvis._id);

        res.status(201).json({
            message: 'Avis publié avec succès',
            avis: savedAvis
        });

    } catch (error) {
        console.error('❌ Erreur POST /api/avis:', error);

        if (error.name === 'ValidationError') {
            const messages = Object.values(error.errors).map(err => err.message);
            return res.status(400).json({
                message: 'Erreur de validation',
                errors: messages
            });
        }

        res.status(500).json({
            message: 'Erreur lors de la publication',
            error: error.message
        });
    }
});

// DELETE /api/avis/:id - Supprimer un avis
router.delete('/:id', async (req, res) => {
    console.log('📥 DELETE /api/avis/' + req.params.id);
    try {
        const avis = await Avis.findByIdAndDelete(req.params.id);
        if (!avis) {
            return res.status(404).json({ message: 'Avis non trouvé' });
        }
        res.status(200).json({ message: 'Avis supprimé' });
    } catch (error) {
        console.error('❌ Erreur DELETE:', error);
        res.status(500).json({ message: 'Erreur serveur', error: error.message });
    }
});

module.exports = router;
