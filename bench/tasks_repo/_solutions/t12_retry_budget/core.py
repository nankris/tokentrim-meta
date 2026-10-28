def run_with_retry(operation, attempts, retry_on, sleep):
    if attempts < 1: raise ValueError('attempts must be positive')
    for index in range(attempts):
        try: return operation()
        except retry_on:
            if index == attempts - 1: raise
            sleep(2 ** index)
def describe_policy(attempts):
    return f'{attempts} total attempts'
