const mongoose = require('mongoose');

const leadSchema = new mongoose.Schema({
    fullName: { type: String, required: true },
    email: { type: String, required: true, unique: true }, // Enforces your unique index constraint
    phoneNumber: { type: String },
    company: { type: String },
    acquisitionSource: { type: String },
    pipelineStage: {
        type: String,
        enum: ['NEW_LEAD', 'QUALIFYING', 'BOOKING_OFFERED', 'CALL_BOOKED', 'NURTURE', 'DISQUALIFIED'],
        default: 'NEW_LEAD'
    },
    qualificationScore: { type: Number, min: 1, max: 10 },
    budgetRange: { type: String },
    serviceInterest: { type: String },
    voiceDisposition: {
        // Embedded subdocument as specified in your architecture
        status: { type: String },
        lastContacted: { type: Date },
        notes: { type: String }
    }
}, {
    timestamps: true // Automatically handles your creation and update timestamps
});

// The first argument 'Lead' will automatically be lowercased and pluralized to 'leads' by Mongoose for the collection name
module.exports = mongoose.model('Lead', leadSchema);