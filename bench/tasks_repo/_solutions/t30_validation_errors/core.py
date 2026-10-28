def _validate(data, name_field, count_field):
    errors = []
    name, count = data.get(name_field), data.get(count_field)
    if not isinstance(name,str) or not name.strip(): errors.append(name_field + '_required')
    if not isinstance(count,int) or isinstance(count,bool) or count < 0:
        errors.append(count_field + '_invalid')
    return errors
def validate_user(data): return _validate(data,'name','age')
def validate_team(data): return _validate(data,'name','size')
def validate_project(data): return _validate(data,'title','seats')
