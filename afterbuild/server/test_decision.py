"""Test decision system with proper prompts"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dialogue_server import DialogueServer
import time

def test_decision():
    """Test Alice's decision making"""
    server = DialogueServer()
    
    # Initialize server
    if not server.load_model():
        print("Failed to load model")
        return
    
    print("\n" + "="*50)
    print("Testing Decision System")
    print("="*50)
    
    # Test contexts
    test_contexts = [
        "Bob is nearby",
        "dog is in sight. Bob is in sight",
        "Sam is nearby. bar is visible",
        "Nothing special happening"
    ]
    
    for context in test_contexts:
        print(f"\nContext: {context}")
        print("-" * 40)
        
        # Make decision
        result = server.make_simple_decision("Alice", context)
        
        print(f"Raw response: {result['raw']}")
        print(f"Action: {result['action']}")
        print(f"Target: {result['target']}")
        print(f"Valid: {result['valid']}")
        print(f"Time: {result['time']:.2f}s")
        
        time.sleep(0.5)  # Small delay between tests
    
    print("\n" + "="*50)
    print("Test Complete")
    print("="*50)

if __name__ == "__main__":
    test_decision()