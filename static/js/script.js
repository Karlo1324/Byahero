// =============================================
// BiyaHero - Smart Commute AI
// JavaScript - Form Handling & Predictions
// =============================================

const predictForm = document.getElementById('predictForm');
const resultsSection = document.getElementById('resultsSection');
const errorSection = document.getElementById('errorSection');

// Form submission handler
predictForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    // Get form values
    const formData = {
        route: document.getElementById('route').value,
        time: document.getElementById('time').value,
        day: document.getElementById('day').value,
        stop: document.getElementById('stop').value,
        crowd: document.querySelector('input[name="crowd"]:checked').value
    };

    // Validate all fields are filled
    if (!formData.route || !formData.time || !formData.day || !formData.stop || !formData.crowd) {
        showError('Please fill in all fields');
        return;
    }

    // Show loading state
    const submitBtn = predictForm.querySelector('.btn-predict');
    const originalText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.classList.add('loading');
    submitBtn.textContent = 'Calculating...';

    try {
        // Send prediction request
        const response = await fetch('/api/predict', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(formData)
        });

        if (!response.ok) {
            throw new Error('Prediction failed');
        }

        const result = await response.json();

        if (result.success) {
            displayResults(result, formData);
        } else {
            showError(result.error || 'Failed to get prediction');
        }
    } catch (error) {
        console.error('Error:', error);
        showError('An error occurred. Please try again.');
    } finally {
        // Restore button state
        submitBtn.disabled = false;
        submitBtn.classList.remove('loading');
        submitBtn.textContent = originalText;
    }
});

// Display results function
function displayResults(result, formData) {
    // Hide error section
    errorSection.style.display = 'none';

    // Update travel time
    document.getElementById('travelTime').textContent = `${result.travel_time} minutes`;

    // Update decision
    const decisionResult = document.getElementById('decisionResult');
    const decisionIcon = document.getElementById('decisionIcon');
    const decisionText = document.getElementById('decisionText');

    if (result.decision === 'leave_now') {
        decisionResult.classList.add('leave-now');
        decisionIcon.textContent = '🚨';
        decisionText.textContent = 'LEAVE NOW!';
    } else {
        decisionResult.classList.remove('leave-now');
        decisionIcon.textContent = '✓';
        decisionText.textContent = 'You Can Wait';
    }

    // Generate insights
    const insights = generateInsights(result, formData);
    document.getElementById('insightsContent').innerHTML = insights;

    // Show results section
    resultsSection.style.display = 'block';
    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Generate insights based on prediction
function generateInsights(result, formData) {
    let insights = '';

    // Travel time insight
    if (result.travel_time > 40) {
        insights += createInsightItem(
            '⏱️',
            'Long Travel Time',
            'This is a longer route. Plan accordingly and leave early to avoid delays.'
        );
    } else if (result.travel_time > 25) {
        insights += createInsightItem(
            '⏰',
            'Moderate Travel Time',
            'This route takes a reasonable amount of time. Leave with enough buffer.'
        );
    } else {
        insights += createInsightItem(
            '⚡',
            'Quick Route!',
            'This is a faster route. You\'ll reach your destination quickly.'
        );
    }

    // Crowd level insight
    if (result.crowd === 'High') {
        insights += createInsightItem(
            '🚨',
            'High Crowd Alert',
            'The bus is crowded. Expect delays and consider arriving early for better seating.'
        );
    } else if (result.crowd === 'Medium') {
        insights += createInsightItem(
            '👥',
            'Moderate Crowd',
            'Standard passenger load. The bus should operate on schedule.'
        );
    } else {
        insights += createInsightItem(
            '👤',
            'Light Crowd',
            'Few passengers today. You\'ll have a comfortable ride with plenty of space.'
        );
    }

    // Decision-based insights
    if (result.decision === 'leave_now') {
        insights += createInsightItem(
            '🚌',
            'Urgent Departure',
            'High crowd levels suggest the bus may depart soon. Don\'t delay!'
        );
    } else {
        insights += createInsightItem(
            '✓',
            'Time to Spare',
            'You can take your time. The bus will wait for more passengers.'
        );
    }

    // Time-of-day insights
    const hour = parseInt(formData.time);
    if ((hour >= 6 && hour < 9) || (hour >= 17 && hour < 18)) {
        insights += createInsightItem(
            '⏲️',
            'Peak Hours',
            'This is a peak commute time. Expect more passengers and potential delays.'
        );
    }

    return insights;
}

// Helper function to create insight items
function createInsightItem(icon, title, text) {
    return `
        <div class="insight-item">
            <div class="insight-icon">${icon}</div>
            <div class="insight-content">
                <div class="insight-title">${title}</div>
                <div class="insight-text">${text}</div>
            </div>
        </div>
    `;
}

// Show error function
function showError(message) {
    errorSection.style.display = 'block';
    document.getElementById('errorMessage').textContent = message;
    resultsSection.style.display = 'none';
    errorSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Reset form function
function resetForm() {
    predictForm.reset();
    resultsSection.style.display = 'none';
    errorSection.style.display = 'none';

    // Uncheck radio buttons
    document.querySelectorAll('input[name="crowd"]').forEach(radio => {
        radio.checked = false;
    });

    // Scroll back to form
    predictForm.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Initialize: Focus on first input on page load
window.addEventListener('load', () => {
    document.getElementById('route').focus();
});
