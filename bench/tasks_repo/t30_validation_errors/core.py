def validate_user(data):
    errors = []
    if not data.get('name'): errors.append('name_required')
    if not isinstance(data.get('age'),int) or data['age'] < 0: errors.append('age_invalid')
    return errors
def validate_team(data):
    errors = []
    if not data.get('name'): errors.append('name_required')
    if not isinstance(data.get('size'),int) or data['size'] < 0: errors.append('size_invalid')
    return errors
def validate_project(data):
    raise NotImplementedError('projects')
