def run_with_retry(operation, attempts, retry_on, sleep):
    for index in range(attempts + 1):
        try: return operation()
        except Exception:
            sleep(2 ** index)
            if index == attempts: raise
def describe_policy(attempts):
    return f'{attempts} total attempts'
