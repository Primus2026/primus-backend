import torch
import numpy as np
import sys

print(f"Python version: {sys.version}")
print(f"Numpy version: {np.__version__}")
print(f"Torch version: {torch.__version__}")

try:
    # Test basic interop
    arr = np.array([1, 2, 3])
    t = torch.from_numpy(arr)
    print("SUCCESS: Torch.from_numpy worked!")
    
    # Test basic tensor creation
    t2 = torch.tensor(arr)
    print("SUCCESS: torch.tensor(numpy_array) worked!")
    
except Exception as e:
    print(f"FAILURE: {e}")
    sys.exit(1)
