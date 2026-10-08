_FUTURE_COLUMNS = frozenset({'forward_labels', 'entry_open', 'return_close_1d', 'return_close_3d', 'return_close_5d', 'return_close_10d', 'mfe_high_5d', 'mae_low_5d', 'entry_reference_price', 'new_low_after_signal', 'false_falling_knife'})

def is_future_feature(name: str) -> bool:
    return name in _FUTURE_COLUMNS or name.startswith(('forward_', 'future_', 'entry_', 'mfe_', 'mae_', 'hit_', 'time_to_', 'up_')) or name.startswith('return_close_')
