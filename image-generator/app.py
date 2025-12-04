"""
Image Generator Service

Main Flask application for generating visualization images
"""
import os
import redis
from flask import Flask, request, jsonify

# Import configuration
from config import (
    REDIS_URL, REDIS_TTL, ENABLED_GENERATORS,
    IMAGE_WIDTH, IMAGE_HEIGHT, IMAGE_DPI,
    print_config
)

# Import generators
from generators import get_enabled_generators, list_all_generators, get_generator_info

# Initialize Flask app
app = Flask(__name__)

# Initialize Redis client
redis_client = redis.from_url(REDIS_URL, decode_responses=False)

# Load enabled generators
generators = get_enabled_generators(ENABLED_GENERATORS)

# Global state storage (for prev_state)
prev_states = {}


@app.route('/generate', methods=['POST'])
def generate():
    """
    Generate images based on current state
    
    Request JSON:
    {
        "exp_id": "experiment_id",
        "step": 0,
        "state": {
            "pressure": 30.0,
            "target_pressure": 120.0,
            "valve_setting": 0.5,
            "flow": 100.0,
            ...
        },
        "history": {
            "pressure": [29.0, 29.5, 30.0],
            "valve_setting": [0.48, 0.49, 0.5],
            ...
        }
    }
    
    Response JSON:
    {
        "redis_keys": {
            "generator_name": "redis_key",
            ...
        },
        "metadata": {
            "generated_at": "timestamp",
            "image_size": [256, 256],
            "enabled_generators": ["gen1", "gen2", ...]
        }
    }
    """
    try:
        data = request.json
        
        exp_id = data.get('exp_id', 'unknown')
        step = data.get('step', 0)
        state = data.get('state', {})
        history = data.get('history', {})
        
        # Get previous state
        prev_state = prev_states.get(exp_id)
        
        # Image size
        size = (IMAGE_WIDTH, IMAGE_HEIGHT)
        
        # Generate images with enabled generators
        redis_keys = {}
        
        for name, generator in generators.items():
            try:
                # Generate image
                img_bytes = generator.generate(state, history, prev_state, size)
                
                # Store in Redis with TTL
                redis_key = f"{exp_id}:step_{step}:{name}"
                redis_client.setex(redis_key, REDIS_TTL, img_bytes)
                
                redis_keys[name] = redis_key
                
            except Exception as e:
                print(f"Error generating {name}: {e}")
                import traceback
                traceback.print_exc()
        
        # Save current state for next iteration
        prev_states[exp_id] = state
        
        # Debug log
        if step % 10 == 0 or step == 0:
            print(f"[image-generator] Generated {len(redis_keys)} images for {exp_id}, step {step}")
        
        return jsonify({
            "redis_keys": redis_keys,
            "metadata": {
                "generated_at": state.get('timestamp', 'unknown'),
                "image_size": [IMAGE_WIDTH, IMAGE_HEIGHT],
                "enabled_generators": list(redis_keys.keys()),
                "num_generators": len(redis_keys)
            }
        })
    
    except Exception as e:
        print(f"Error in /generate endpoint: {e}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "error": str(e)
        }), 500


@app.route('/info', methods=['GET'])
def info():
    """
    Get information about available generators
    
    Response JSON:
    {
        "enabled_generators": ["gen1", "gen2", ...],
        "available_generators": ["gen1", "gen2", ...],
        "generator_info": {...}
    }
    """
    return jsonify({
        "enabled_generators": ENABLED_GENERATORS,
        "available_generators": list_all_generators(),
        "generator_info": get_generator_info(),
        "config": {
            "image_size": [IMAGE_WIDTH, IMAGE_HEIGHT],
            "image_dpi": IMAGE_DPI,
            "redis_ttl": REDIS_TTL
        }
    })


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    try:
        # Test Redis connection
        redis_client.ping()
        redis_status = "ok"
    except Exception as e:
        redis_status = f"error: {e}"
    
    return jsonify({
        "status": "healthy" if redis_status == "ok" else "degraded",
        "redis": redis_status,
        "enabled_generators": len(generators),
        "available_generators": len(list_all_generators())
    })


@app.route('/reset', methods=['POST'])
def reset():
    """
    Reset previous states (useful for debugging)
    """
    global prev_states
    prev_states = {}
    
    return jsonify({
        "status": "reset",
        "message": "Previous states cleared"
    })


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🎨 Image Generator Service Starting")
    print("=" * 60)
    print()
    
    # Print configuration
    print_config()
    
    print()
    print(f"Loaded {len(generators)} generators:")
    for name in generators.keys():
        print(f"  ✓ {name}")
    
    print()
    print("Starting Flask app on 0.0.0.0:5000")
    print("=" * 60)
    print()
    
    app.run(host='0.0.0.0', port=5000, debug=False)