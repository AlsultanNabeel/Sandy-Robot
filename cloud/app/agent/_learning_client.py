_fn = None

def set_learning_completion_fn(fn):
    global _fn
    _fn = fn

def get_learning_completion_fn():
    if _fn is None:
        raise RuntimeError("Learning completion fn not set")
    return _fn