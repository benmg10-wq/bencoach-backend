const mongoose = require('mongoose');

const avisSchema = new mongoose.Schema({
    nom: {
        type: String,
        required: [true, 'Le nom est requis'],
        trim: true,
        maxlength: [50, 'Le nom ne peut pas dépasser 50 caractères']
    },
    pack: {
        type: String,
        required: [true, 'Le pack est requis'],
        enum: ['Starter', 'Premium', 'Elite']
    },
    note: {
        type: Number,
        required: [true, 'La note est requise'],
        min: [1, 'La note minimum est 1'],
        max: [5, 'La note maximum est 5']
    },
    resultat: {
        type: String,
        trim: true,
        maxlength: [100, 'Le résultat ne peut pas dépasser 100 caractères']
    },
    texte: {
        type: String,
        required: [true, 'Le témoignage est requis'],
        trim: true,
        minlength: [10, 'Le témoignage doit faire au moins 10 caractères'],
        maxlength: [1000, 'Le témoignage ne peut pas dépasser 1000 caractères']
    }
}, {
    timestamps: true
});

avisSchema.index({ createdAt: -1 });

module.exports = mongoose.model('Avis', avisSchema);
