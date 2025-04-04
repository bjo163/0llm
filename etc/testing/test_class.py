from g4f.Provider import __all__, ProviderUtils
from g4f import ChatCompletion
import concurrent.futures
import os
from datetime import datetime

# Buat folder output & log
base_dir = os.path.dirname(__file__)
output_dir = os.path.join(base_dir, '..', '..', 'output')
debug_dir = os.path.join(output_dir, 'debug')
os.makedirs(output_dir, exist_ok=True)
os.makedirs(debug_dir, exist_ok=True)

timestamp = datetime.now().strftime('%d%m%Y-%H%M')
log_file_path = os.path.join(output_dir, f'{timestamp}-test_provider.txt')
debug_log_path = os.path.join(debug_dir, f'{timestamp}-provider_debug.txt')

def get_status_label(working: bool, needs_auth: bool) -> str:
    if needs_auth:
        return '🔒 needs_auth'
    if not working:
        return '🔴 not working'
    return '🟢 working'

def test_provider(provider):
    try:
        provider_obj = ProviderUtils.convert[provider]
        status_label = get_status_label(provider_obj.working, provider_obj.needs_auth)
        debug_lines = []

        debug_lines.append(f"\n[DEBUG] Testing provider: {provider_obj.__name__}")
        debug_lines.append(f"[DEBUG] Attributes: {dir(provider_obj)}")
        debug_lines.append(f"[DEBUG] Dict: {getattr(provider_obj, '__dict__', {})}")
        supported = getattr(provider_obj, "supported_models", [])
        debug_lines.append(f"[DEBUG] Supported models: {supported}")

        for line in debug_lines:
            print(line)

        with open(debug_log_path, "a") as debug_file:
            debug_file.write("\n".join(debug_lines) + "\n")

        # Coba kirim request jika working dan tidak butuh auth
        if provider_obj.working and not provider_obj.needs_auth:
            if 'gpt-3.5-turbo' not in supported:
                result = f"❌ {timestamp}-test_provider | {provider_obj.__name__} | ❗ no compatible model | Skipped"
                print(result)
                return result

            completion = ChatCompletion.create(
                model='gpt-3.5-turbo',
                messages=[{"role": "user", "content": "hello"}],
                provider=provider_obj
            )
            result = f"✅ {timestamp}-test_provider | {provider_obj.__name__} | {status_label} | Model: gpt-3.5-turbo | Method: ChatCompletion.create | {completion}"
            print(result)
            return result
        else:
            result = f"❌ {timestamp}-test_provider | {provider_obj.__name__} | {status_label} | Skipped"
            print(result)
            return result

    except Exception as e:
        error_msg = f"❌ {timestamp}-test_provider | {provider} | Failed to get response | Error: {e}"
        print(error_msg)
        with open(debug_log_path, "a") as debug_file:
            debug_file.write(error_msg + "\n")
        return error_msg

# Jalankan semua provider tanpa terkecuali
with concurrent.futures.ThreadPoolExecutor() as executor:
    futures = [executor.submit(test_provider, provider) for provider in __all__]
    with open(log_file_path, 'w') as f:
        for future in concurrent.futures.as_completed(futures):
            if result := future.result():
                f.write(result + '\n')
