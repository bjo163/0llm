import asyncio  # For concurrency
import datetime
import hashlib
import inspect  # To get provider file info
import json
import os
import re
import time
import traceback  # For detailed error logging

import aiohttp  # For async HTTP requests
import requests  # Still used for synchronous fallback/initial check if needed
from tqdm.asyncio import tqdm  # Async-compatible tqdm

# Assuming g4f is installed and these imports are correct
# If g4f structure changed, these might need adjustment
try:
    from g4f import ChatCompletion
    from g4f.Provider import BaseProvider, ProviderUtils
except ImportError:
    print(
        "Error: g4f library not found or imports failed. Testing functionality might be limited."
    )

    # Dummy classes remain the same
    class Client:
        pass

    class ChatCompletion:
        @staticmethod
        def create(*args, **kwargs):  # Sync dummy
            provider_name = getattr(kwargs.get("provider"), "name", "UnknownProvider")
            prompt_content = kwargs.get("messages", [{}])[0].get("content", "").lower()
            model_used = kwargs.get("model", "unknown")
            print(
                f"Warning: g4f dummy sync ChatCompletion.create called for '{provider_name}'"
            )
            time.sleep(
                0.1 + hash(provider_name + prompt_content) % 5 / 10
            )  # Simulate sync blocking
            if "Fail" in provider_name:
                raise Exception("Provider not working (dummy error)")
            if "Auth" in provider_name:
                raise Exception("Authentication required (dummy error)")
            if "Slow" in provider_name:
                time.sleep(3 + hash(prompt_content) % 3)
                return f"Dummy slow response for: {prompt_content}"
            if "Fallback" in provider_name and model_used == "gpt-3.5-turbo":
                raise Exception(
                    "Model is not supported. Valid models: ['fallback-model']"
                )
            if "Fallback" in provider_name and model_used == "fallback-model":
                return f"Dummy fallback response for: {prompt_content}"
            return f"Dummy successful response for: {prompt_content}"

        # Add dummy async method if needed for type hinting/structure
        # @staticmethod
        # async def acreate(*args, **kwargs):
        #     # Simulate async behavior if needed, or wrap sync for dummy
        #     await asyncio.sleep(0.1)
        #     try:
        #         return ChatCompletion.create(*args, **kwargs)
        #     except Exception as e:
        #         raise e

    class ProviderUtils:
        class DummyProviderBase:
            __module__ = "dummy_providers"
            try:
                _dummy_file_path = os.path.join(
                    os.path.dirname(__file__), "dummy_provider_src.py"
                )
                __file__ = _dummy_file_path
            except NameError:
                __file__ = "dummy_provider_src.py"
            if not os.path.exists(
                __file__
            ):  # Ensure dummy file exists if needed by get_provider_details
                try:
                    os.makedirs(os.path.dirname(__file__), exist_ok=True)
                    open(__file__, "a").close()
                except:
                    pass  # Ignore errors creating dummy file

            def __init__(self, name="Dummy", needs_auth=False, url="http://dummy.com"):
                self.name = name
                self.needs_auth = needs_auth
                self.url = url
                self._internal_var = "secret"

        class ExampleWorkingProvider(DummyProviderBase):
            pass

        class ExampleSlowProvider(DummyProviderBase):
            pass

        class ExampleAuthProvider(DummyProviderBase):
            pass

        class ExampleFailProvider(DummyProviderBase):
            pass

        class ExampleFallbackProvider(DummyProviderBase):
            pass

        class ExampleWorkingUnstable(DummyProviderBase):
            pass

        convert = {
            "ExampleWorkingProvider": ExampleWorkingProvider(
                name="ExampleWorkingProvider",
                needs_auth=False,
                url="http://working.com",
            ),
            "ExampleSlowProvider": ExampleSlowProvider(
                name="ExampleSlowProvider", needs_auth=False, url="http://slow.com"
            ),
            "ExampleAuthProvider": ExampleAuthProvider(
                name="ExampleAuthProvider", needs_auth=True, url="http://auth.com"
            ),
            "ExampleFailProvider": ExampleFailProvider(
                name="ExampleFailProvider", needs_auth=False, url="http://fail.com"
            ),
            "ExampleFallbackProvider": ExampleFallbackProvider(
                name="ExampleFallbackProvider",
                needs_auth=False,
                url="http://fallback.com",
            ),
            "ExampleWorkingUnstable": ExampleWorkingUnstable(
                name="ExampleWorkingUnstable",
                needs_auth=False,
                url="http://unstable.com",
            ),
        }


# --- Configuration ---
CONFIG = {
    "db_path": ".cache/db/provider.json",
    "ai_solution_endpoint_url": "http://160.22.193.9:1337/v1/chat/completions?provider=ASD",
    "ai_solution_model": "gpt-4o",
    "request_timeout": 60,  # Timeout for external AI calls
    "provider_test_timeout": 45,  # Timeout for individual g4f calls
    "max_source_code_length": 10000,
    "max_concurrent_tests": 10,  # Limit concurrency
    "test_prompts": [
        {"type": "greeting", "content": "hello"},
        {"type": "question", "content": "What is the capital of France?"},
        {"type": "instruction", "content": "Translate 'good morning' to Spanish"},
    ],
    "skip_working_ai_calls": True,  # Skip AI calls for providers marked ✅ Working / ✅ Mostly Working
}

# Use prompts from config
PROMPTS_TO_RUN = CONFIG["test_prompts"][:3]  # Use first 3 or adjust slice

# --- Global Lock for Synchronous File I/O ---
# Using asyncio Lock is generally preferred in async code, but file I/O can be tricky.
# A simple threading Lock combined with sync file operations might be safer if concurrency issues arise.
# For this version, sticking to the synchronous file lock approach within the async flow.
db_file_lock = (
    asyncio.Lock()
)  # Use asyncio Lock for coordinating access to sync file ops

# --- SECURITY WARNING ---
print("\033[91m" + "=" * 80)
print("SECURITY WARNING:")
print("This script may send provider source code and parameters")
print(f"to an external AI endpoint ({CONFIG['ai_solution_endpoint_url']}).")
print("REVIEW THE CODE AND THE AI ENDPOINT'S PRIVACY POLICY BEFORE RUNNING.")
print("Ensure you TRUST the external endpoint and understand the risks.")
print("=" * 80 + "\033[0m")
# time.sleep(3) # Removed pause for faster execution, warning is clear

# --- Helper Functions ---


def generate_provider_id(provider_name):
    if not provider_name:
        return None
    hash_object = hashlib.sha1(provider_name.encode("utf-8"))
    return hash_object.hexdigest()[:12]


# Note: load_results and update_database_entry remain synchronous for file I/O safety
# but acquire the asyncio lock before operating.


def load_results_sync(db_path=CONFIG["db_path"]):
    """Synchronous load, ensures source code is removed."""
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    item.pop("provider_source_code", None)
                return data
        except json.JSONDecodeError:
            print(f"Warning: Could not decode JSON from {db_path}. Starting empty.")
            return []
        except Exception as e:
            print(f"Error loading {db_path}: {e}. Starting empty.")
            return []
    return []


async def update_database_entry(new_result, db_path=CONFIG["db_path"]):
    """Async wrapper to load, update/append a single entry, and save the database safely."""
    if not new_result or "id" not in new_result:
        print("Error: Invalid result passed to update_database_entry.")
        return

    entry_to_save = new_result.copy()
    entry_to_save.pop("provider_source_code", None)
    entry_id = entry_to_save["id"]

    # Acquire the asyncio lock before performing synchronous file I/O
    async with db_file_lock:
        try:
            # Load data synchronously inside the lock
            all_data = load_results_sync(db_path)

            # Find and update or append (logic remains the same)
            found = False
            for i, existing_item in enumerate(all_data):
                if existing_item.get("id") == entry_id:
                    if "rank" in existing_item and "rank" not in entry_to_save:
                        entry_to_save["rank"] = existing_item["rank"]
                    if (
                        "ai_solution" not in entry_to_save
                        or not entry_to_save["ai_solution"]
                        or "N/A" in entry_to_save["ai_solution"]
                    ):
                        if existing_item.get(
                            "ai_solution"
                        ) and "N/A" not in existing_item.get("ai_solution"):
                            entry_to_save["ai_solution"] = existing_item["ai_solution"]
                    if "tags" not in entry_to_save or not entry_to_save["tags"]:
                        if existing_item.get("tags"):
                            entry_to_save["tags"] = existing_item["tags"]
                    all_data[i] = entry_to_save
                    found = True
                    break
            if not found:
                all_data.append(entry_to_save)

            # Save updated data using temporary file (sync operations)
            temp_path = db_path + ".tmp"
            try:
                all_data.sort(
                    key=lambda x: x.get("id", "")
                )  # Sort by ID for consistency
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(all_data, f, indent=2, ensure_ascii=False)
                os.replace(temp_path, db_path)
            except Exception as e:
                print(f"\nError saving updated data sync to {db_path}: {e}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)  # Clean up temp file on error

        except Exception as e:
            # Catch errors during the locked operation
            print(f"\nError during locked database update for {entry_id}: {e}")
        # Lock is automatically released when exiting 'async with' block


# Note: save_final_ranked_results also needs to acquire the lock
async def save_final_ranked_results(data, db_path=CONFIG["db_path"]):
    """Saves the final ranked list, acquires lock."""
    data_to_save = []
    for item in data:
        saved_item = item.copy()
        saved_item.pop("provider_source_code", None)
        data_to_save.append(saved_item)
    data_to_save.sort(key=lambda x: (x.get("rank", float("inf")), x.get("id", "")))

    async with db_file_lock:  # Acquire lock for final save
        try:
            temp_path = db_path + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, indent=2, ensure_ascii=False)
            os.replace(temp_path, db_path)
            print(f"\n💾 Final ranked results saved to {db_path}.")
        except Exception as e:
            print(f"\nError saving final ranked results to {db_path}: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)


# --- Core Logic (Status, Advice, Score - remain synchronous) ---
ADVICE_MAP = {
    "✅ Working": "Stabil.",
    "✅ Mostly Working": "Sebagian besar OK.",
    "⏳ Slow Response": "Lambat.",
    "⚠️ Unstable": "Tidak Stabil.",
    "🔒 Needs Auth": "Butuh Auth.",
    "❌ Fallback Failed": "Fallback Gagal.",
    "❌ Not Working": "Tidak Bekerja.",
    "❓ Unknown": "Tidak Diketahui.",
}  # Shorter advice map


def generate_advice(status, error=None, needs_auth=False, success_ratio=1.0):
    base = ADVICE_MAP.get(status, ADVICE_MAP["❓ Unknown"])
    if status == "✅ Mostly Working":
        base += f" ({int(success_ratio * 100)}% OK)"
    # Simplified hints
    if error:
        error_lower = str(error).lower()
        if "auth" in error_lower or "key" in error_lower:
            base = ADVICE_MAP["🔒 Needs Auth"]
        elif "rate limit" in error_lower:
            base += " (Rate Limit?)"
        elif (
            "connection" in error_lower
            or "network" in error_lower
            or "timeout" in error_lower
        ):
            base += " (Network Error?)"
        elif "model" in error_lower and (
            "support" in error_lower or "found" in error_lower
        ):
            base += " (Model Error?)"
    if status == "🔒 Needs Auth" and not needs_auth:
        base += " (Auth Terdeteksi!)"
    return base


def evaluate_status_from_logs(logs, needs_auth=False):
    if not logs:
        return "❓ Unknown"
    latest_log = logs[-1]
    prompts_tested = latest_log.get("prompts_tested_count", 0)
    prompts_succeeded = latest_log.get("prompts_successful_count", 0)
    avg_response_time = latest_log.get("response_time")
    error = latest_log.get("error")
    fallback_failed = latest_log.get("status") == "❌ Fallback Failed"
    if prompts_tested == 0:
        return "❓ Unknown"
    success_ratio = prompts_succeeded / prompts_tested if prompts_tested > 0 else 0
    auth_error_detected = (
        "auth" in (error or "").lower() or "key" in (error or "").lower()
    )
    if needs_auth or auth_error_detected:
        if needs_auth and (success_ratio == 0 or auth_error_detected):
            return "🔒 Needs Auth"
    if success_ratio == 0:
        return "❌ Fallback Failed" if fallback_failed else "❌ Not Working"
    if 0 < success_ratio < 1:
        return "⚠️ Unstable"
    if (
        success_ratio == 1.0
        and avg_response_time is not None
        and avg_response_time > 15
    ):
        return "⏳ Slow Response"
    if success_ratio == 1.0:
        return "✅ Working"
    return "❓ Unknown"


def calculate_score(result):
    score = 0
    prompts_tested = result.get("prompts_tested_count", 0)
    prompts_succeeded = result.get("prompts_successful_count", 0)
    response_time = result.get("response_time")
    fallback = result.get("fallback", False)
    status = result.get("status", "❓ Unknown")
    if prompts_tested == 0:
        return 1
    success_ratio = prompts_succeeded / prompts_tested
    if success_ratio == 1.0:
        score += 70
    elif success_ratio >= 0.5:
        score += 40
    else:
        score += 10
    if success_ratio == 1.0:
        score += 10
    if prompts_succeeded > 0 and response_time is not None:
        if response_time < 3:
            score += 20
        elif response_time < 7:
            score += 10
        elif response_time < 15:
            score += 5
    if status == "⏳ Slow Response":
        score -= 15
    elif status == "⚠️ Unstable":
        score -= 25
    elif status == "🔒 Needs Auth":
        score -= 10
    elif status == "❌ Fallback Failed":
        score -= 35
    elif status == "❌ Not Working":
        score -= 30
    if fallback:
        score -= 10
    return max(1, min(100, int(score)))


def rank_providers(all_data):
    """Calculates scores and ranks providers IN MEMORY."""
    print("\n📊 Memulai proses ranking provider (in-memory)...")
    if not all_data:
        print("📦 Tidak ada data untuk diranking.")
        return []
    for res in all_data:
        res["score"] = calculate_score(res)
    sorted_providers = sorted(
        all_data,
        key=lambda r: (
            r.get("score", 0),
            r.get("prompts_successful_count", 0) / r.get("prompts_tested_count", 1),
            r.get("id", ""),
        ),
        reverse=True,
    )
    print("\n🏅 Hasil Peringkat Sementara:")
    for rank, res in enumerate(sorted_providers, 1):
        res["rank"] = rank  # Assign rank in memory
        success_ratio_str = f"{res.get('prompts_successful_count', '?')}/{res.get('prompts_tested_count', '?')}"
        tags_str = f" T:[{', '.join(res.get('tags', []))}]" if res.get("tags") else ""
        tqdm.write(
            f"  {rank}. {res.get('provider', 'N/A')[:20]:<20} (S:{res.get('score', 'N/A'):>3}, OK:{success_ratio_str:<5}) {tags_str}"
        )  # Align output
    print("\033[92m✅ Ranking selesai (peringkat akan disimpan di akhir).\033[0m")
    return sorted_providers


def get_provider_details(provider_obj):
    """Gets provider details (sync function)."""
    details = {
        "provider_file_path": "N/A",
        "provider_source_code": "N/A",
        "provider_parameters": {},
    }
    if provider_obj is None:
        return details
    try:
        provider_class = provider_obj.__class__
        file_path = inspect.getfile(provider_class)
        details["provider_file_path"] = file_path
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    details["provider_source_code"] = f.read()
            except Exception as e:
                details["provider_source_code"] = f"Error reading file: {e}"
        else:
            details["provider_source_code"] = "File path found but file does not exist."
    except Exception:
        details["provider_file_path"] = "N/A (built-in/dynamic?)"  # Simplified error
    try:
        params = {
            k: repr(v)
            for k, v in provider_obj.__dict__.items()
            if not k.startswith("_") and not callable(v)
        }
        details["provider_parameters"] = params
    except Exception:
        details["provider_parameters"] = {"error": "Failed to get parameters"}
    return details


# --- Async External AI Calls ---


async def _call_external_ai_async(session, payload, purpose="solusi"):
    """Async function to make the POST request using aiohttp session."""
    url = CONFIG["ai_solution_endpoint_url"]
    timeout = aiohttp.ClientTimeout(total=CONFIG["request_timeout"])
    headers = {"accept": "application/json", "Content-Type": "application/json"}
    try:
        async with session.post(
            url, json=payload, headers=headers, timeout=timeout
        ) as response:
            response.raise_for_status()  # Check for HTTP errors
            response_json = await response.json()
            if (
                response_json
                and "choices" in response_json
                and len(response_json["choices"]) > 0
            ):
                message = response_json["choices"][0].get("message")
                if message and "content" in message:
                    return message["content"].strip()
                else:
                    return f"Gagal ({purpose}): 'message'/'content' field missing."
            else:
                return f"Gagal ({purpose}): 'choices' field missing/empty."
    except asyncio.TimeoutError:
        return f"Gagal ({purpose}): Timeout ({CONFIG['request_timeout']}s)."
    except aiohttp.ClientError as e:
        return f"Gagal ({purpose}): {type(e).__name__} - {e}"
    except json.JSONDecodeError:
        return f"Gagal ({purpose}): Respons JSON tidak valid."
    except Exception as e:
        return f"Gagal ({purpose}): {type(e).__name__} - {e}"


async def query_openai_solution_async(session, result):
    """Async: Queries the external AI for troubleshooting & analysis."""
    # Warning for external endpoint
    # if not CONFIG["ai_solution_endpoint_url"].startswith("http://localhost"): print("\033[91m      W (Solusi): Ext!\033[0m", end='')

    params_str = json.dumps(
        result.get("provider_parameters", {}), indent=2, default=str
    )
    source_code = result.get("provider_source_code", "N/A")
    if len(source_code) > CONFIG["max_source_code_length"]:
        source_code = (
            source_code[: CONFIG["max_source_code_length"]] + "\n\n... [TRUNCATED]"
        )
        # print("\n      I (Solusi): Truncated.", end='')

    user_prompt = (
        f"Analisis Masalah & Kode Provider API LLM:\n"
        f"Provider: {result.get('provider', 'N/A')} (ID: {result.get('id', 'N/A')}), Status: {result.get('status', 'N/A')}\n"
        f"Hasil: {result.get('prompts_successful_count', 'N/A')}/{result.get('prompts_tested_count', 'N/A')} OK, AvgTime: {result.get('response_time', 'N/A')}s\n"
        f"Error: {result.get('error', 'Tidak ada')}\n"
        f"Path: {result.get('provider_file_path', 'N/A')}\n"
        f"Params:\n{params_str}\n"
        f"Code:\n```python\n{source_code}\n```\n"
        f"Tugas: 1. Advice Troubleshooting (penyebab utama, 3-5 langkah solusi). 2. Analisa Kode & Param (2-4 potensi masalah).\nBhs Indonesia."
    )
    payload = {
        "messages": [
            {
                "role": "system",
                "content": "AI engineer ahli troubleshoot & analisis kode Python LLM. Bhs Indonesia.",
            },
            {"role": "user", "content": user_prompt},
        ],
        "model": CONFIG["ai_solution_model"],
        "provider": "",
        "stream": False,
    }
    return await _call_external_ai_async(session, payload, purpose="solusi & analisa")


async def query_ai_tags_async(session, result):
    """Async: Queries the external AI to generate descriptive tags."""
    # if not CONFIG["ai_solution_endpoint_url"].startswith("http://localhost"): print("\033[91m      W (Tags): Ext!\033[0m", end='')

    error_summary = (result.get("error") or "Tidak ada")[:100]
    user_prompt = (
        f"Generate Tags Provider LLM:\n"
        f"Provider: {result.get('provider', 'N/A')}, Status: {result.get('status', 'N/A')}\n"
        f"Hasil: {result.get('prompts_successful_count', 'N/A')}/{result.get('prompts_tested_count', 'N/A')} OK, AvgTime: {result.get('response_time', 'N/A')}s\n"
        f"Auth:{'Y' if result.get('needs_auth_flag', False) else 'N'}, Fallback:{'Y' if result.get('fallback', False) else 'N'}\n"
        f"Error: {error_summary}\n"
        f"Tugas: Berikan 2-5 tag deskriptif (stabilitas, kecepatan, auth, masalah utama). Contoh: Stable, Fast, NeedsAuth, Unstable, Slow, CodeIssue, FreeTier.\n"
        f"Format Output: Hanya tag dipisahkan koma (contoh: Tag1, Tag2)"
    )
    payload = {
        "messages": [
            {
                "role": "system",
                "content": "Berikan 2-5 tag deskriptif singkat provider LLM. Output HANYA tag dipisah koma.",
            },
            {"role": "user", "content": user_prompt},
        ],
        "model": CONFIG["ai_solution_model"],
        "provider": "",
        "stream": False,
    }
    raw_tags_response = await _call_external_ai_async(session, payload, purpose="tags")
    if raw_tags_response and "Gagal" not in raw_tags_response:
        tags = [tag.strip() for tag in raw_tags_response.split(",") if tag.strip()]
        return tags[:5]
    else:
        return []  # Return empty list on failure


# --- Async Provider Testing ---


async def run_g4f_create_async(provider_obj, model, messages):
    """Runs the synchronous g4f ChatCompletion.create in a thread."""
    loop = asyncio.get_running_loop()
    try:
        # Use asyncio.to_thread to run the potentially blocking sync call
        response = await asyncio.to_thread(
            ChatCompletion.create,
            model=model,
            messages=messages,
            provider=provider_obj,
            # Pass other necessary kwargs if ChatCompletion.create needs them
        )
        return response
    except Exception as e:
        # print(f"Debug: Exception in run_g4f_create_async: {e}") # Debug print
        raise e  # Re-raise the exception to be caught by the caller


async def test_single_prompt(
    provider_obj, prompt_info, current_model_to_use, prompt_index
):
    """Async function to test a single prompt against a provider."""
    prompt_content = prompt_info["content"]
    prompt_type = prompt_info["type"]
    start_time = time.time()
    prompt_success = False
    prompt_error = None
    prompt_duration = 0
    response_str = None

    try:
        # Use asyncio.wait_for for timeout on the g4f call
        response = await asyncio.wait_for(
            run_g4f_create_async(
                provider_obj,
                current_model_to_use,
                [{"role": "user", "content": prompt_content}],
            ),
            timeout=CONFIG["provider_test_timeout"],
        )
        prompt_duration = round(time.time() - start_time, 2)
        prompt_success = True
        response_str = str(
            response
        )  # Store response if needed later, currently not used much
    except asyncio.TimeoutError:
        prompt_duration = round(time.time() - start_time, 2)
        prompt_error = f"Timeout after {CONFIG['provider_test_timeout']}s"
    except Exception as e:
        prompt_duration = round(time.time() - start_time, 2)
        prompt_error = str(e)
        # traceback.print_exc() # Uncomment for full traceback during debugging

    # Log outcome (can be made less verbose)
    status_char = "✅" if prompt_success else "❌"
    tqdm.write(
        f"    - P{prompt_index + 1} [{prompt_type}] '{current_model_to_use[:15]}' {status_char} ({prompt_duration}s){' Err: ' + prompt_error[:50] + '...' if prompt_error else ''}"
    )

    return {
        "type": prompt_type,
        "model_used": current_model_to_use,
        "success": prompt_success,
        "duration": prompt_duration,
        "error": prompt_error,
    }


async def test_provider_async(provider_name, provider_obj, session, semaphore):
    """Async: Tests a single provider with multiple prompts, calls AI, returns full result."""
    async with semaphore:  # Control concurrency
        # tqdm.write(f"\n🧪 Pengujian Async: {provider_name}") # tqdm handles description now
        provider_id = generate_provider_id(provider_name)
        if not provider_id:
            return None  # Cannot proceed without ID

        # Get provider details (synchronously, acceptable as it's mostly CPU/local I/O)
        provider_details = get_provider_details(provider_obj)
        # tqdm.write(f"  -> Path: {os.path.basename(provider_details['provider_file_path'])}")

        now = datetime.datetime.now().isoformat()
        needs_auth = getattr(provider_obj, "needs_auth", False)

        prompt_results_agg = []  # To store results from await asyncio.gather
        successful_prompts_count = 0
        total_duration_successful = 0
        combined_errors = []
        used_fallback_model = None
        initial_model = "gpt-3.5-turbo"

        current_model_to_use = initial_model
        # First prompt test (sequential to check for fallback)
        first_prompt_result = await test_single_prompt(
            provider_obj, PROMPTS_TO_RUN[0], current_model_to_use, 0
        )
        prompt_results_agg.append(first_prompt_result)

        # Check for fallback based on first prompt result
        if not first_prompt_result["success"] and first_prompt_result["error"]:
            prompt_error = first_prompt_result["error"]
            if (
                "Model is not supported" in prompt_error
                or "Invalid model" in prompt_error
            ):
                match = re.search(
                    r"(?:Valid|Available|Supported)\smodels?:\s*(\[.*?\]|\{.*?\}|\S+)",
                    prompt_error,
                    re.IGNORECASE,
                )
                if match:
                    models_str = match.group(1)
                    extracted_fallback = None
                    try:
                        if models_str.startswith("["):
                            valid_models = eval(models_str)
                        elif models_str.startswith("{"):
                            valid_models = list(eval(models_str))
                        else:
                            valid_models = [models_str.strip("'\"")]
                        if valid_models:
                            for model in valid_models:
                                if model != initial_model:
                                    extracted_fallback = model
                                    break
                            if extracted_fallback:
                                tqdm.write(
                                    f"      ♻️ Fallback activated: '{extracted_fallback}' for {provider_name}"
                                )
                                used_fallback_model = extracted_fallback
                    except Exception:
                        pass

        # Run remaining prompts concurrently if any
        remaining_prompts = PROMPTS_TO_RUN[1:]
        if remaining_prompts:
            current_model_to_use = (
                used_fallback_model or initial_model
            )  # Use fallback if activated
            tasks = [
                test_single_prompt(
                    provider_obj, prompt_info, current_model_to_use, i + 1
                )
                for i, prompt_info in enumerate(remaining_prompts)
            ]
            remaining_results = await asyncio.gather(*tasks)
            prompt_results_agg.extend(remaining_results)

        # Aggregate results from all prompts
        for res in prompt_results_agg:
            if res["success"]:
                successful_prompts_count += 1
                total_duration_successful += res["duration"]
            if res["error"]:
                combined_errors.append(f"P[{res['type']}]: {res['error'][:100]}...")

        # Final result object construction (same as before)
        overall_success = successful_prompts_count > 0
        avg_response_time = (
            total_duration_successful / successful_prompts_count
            if successful_prompts_count > 0
            else None
        )
        final_error_message = "; ".join(combined_errors) if combined_errors else None

        result = {
            "id": provider_id,
            "timestamp": now,
            "provider": provider_name,
            "model_tested": initial_model,
            "prompts_tested_count": len(PROMPTS_TO_RUN),
            "prompts_successful_count": successful_prompts_count,
            "success": overall_success,
            "fallback": used_fallback_model is not None,
            "fallback_model_used": used_fallback_model,
            "response_time": avg_response_time,
            "error": final_error_message,
            "needs_auth_flag": needs_auth,
            "provider_file_path": provider_details["provider_file_path"],
            "provider_source_code": provider_details[
                "provider_source_code"
            ],  # Temp included
            "provider_parameters": provider_details["provider_parameters"],
            "status": "❓ Unknown",
            "advice": None,
            "ai_solution": None,
            "tags": [],
            "score": 0,
            "rank": None,
        }

        # Status Evaluation, Advice (Sync functions)
        result["status"] = evaluate_status_from_logs([result], needs_auth)
        if result["fallback"] and successful_prompts_count == 0:
            result["status"] = "❌ Fallback Failed"  # Refined fallback fail status
        success_ratio = (
            successful_prompts_count / len(PROMPTS_TO_RUN)
            if len(PROMPTS_TO_RUN) > 0
            else 0
        )
        result["advice"] = generate_advice(
            result["status"], result["error"], needs_auth, success_ratio
        )

        # Async AI Calls (if needed)
        ai_analysis_needed = (
            result["status"] not in ["✅ Working", "✅ Mostly Working"]
            and CONFIG["skip_working_ai_calls"] == False
            or result["status"] not in ["✅ Working", "✅ Mostly Working"]
            and CONFIG["skip_working_ai_calls"] == True
            and result["status"] != "⏳ Slow Response"
        )  # Also skip slow if skip_working is true

        ai_tasks = []
        if ai_analysis_needed:
            tqdm.write(f"  🤖 Queuing Solusi/Analisa AI for {provider_name}...")
            ai_tasks.append(query_openai_solution_async(session, result))
        else:
            result["ai_solution"] = "N/A (Skipped/Working)"
            ai_tasks.append(
                asyncio.sleep(0, result="N/A (Skipped/Working)")
            )  # Placeholder task

        tqdm.write(f"  🏷️ Queuing Tags AI for {provider_name}...")
        ai_tasks.append(query_ai_tags_async(session, result))

        # Run AI calls concurrently
        ai_results = await asyncio.gather(*ai_tasks)

        # Assign results back (handling potential N/A placeholders)
        if ai_results[0] != "N/A (Skipped/Working)":
            result["ai_solution"] = ai_results[0]
        result["tags"] = ai_results[1] if isinstance(ai_results[1], list) else []

        # Log AI outcomes
        tqdm.write(
            f"  💡 Solusi AI ({provider_name}): {'OK' if result['ai_solution'] and 'Gagal' not in result['ai_solution'] else ('Skipped' if 'N/A' in result['ai_solution'] else 'FAIL')}"
        )
        tqdm.write(
            f"  🏷️ Tags AI ({provider_name}): {'OK' if result['tags'] else 'FAIL'}"
        )

        success_ratio_str = f"{result.get('prompts_successful_count', '?')}/{result.get('prompts_tested_count', '?')}"
        tqdm.write(
            f"🏁 Hasil Async '{provider_name}': Status={result['status']}, OK: {success_ratio_str}, Time: {result['response_time'] or 'N/A'}s"
        )

        # Update database immediately after processing this provider
        await update_database_entry(result)

        return result  # Return result (might not be strictly needed if DB update happens here)


async def test_all_providers_async():
    """Main async function to test all providers concurrently."""
    print(
        f"🚀 Memulai Pengujian Async ({len(PROMPTS_TO_RUN)} prompt, maks {CONFIG['max_concurrent_tests']} konkurensi)..."
    )
    initial_data = load_results_sync()  # Load sync at start
    print(f"💾 Ditemukan {len(initial_data)} data provider (akan diupdate).")

    try:
        all_provider_names = list(ProviderUtils.convert.keys())
    except Exception as e:
        print(f"FATAL: Gagal mendapatkan daftar provider: {e}")
        return
    print(f"🔍 Ditemukan {len(all_provider_names)} provider untuk diuji.")

    semaphore = asyncio.Semaphore(CONFIG["max_concurrent_tests"])
    tasks = []
    connector = aiohttp.TCPConnector(
        limit_per_host=CONFIG["max_concurrent_tests"]
    )  # Limit connections per host for AI endpoint
    async with aiohttp.ClientSession(
        connector=connector
    ) as session:  # Create one session
        for provider_name in all_provider_names:
            try:
                provider_obj = ProviderUtils.convert.get(provider_name)
            except Exception as e:
                print(f"❓ Gagal get obj '{provider_name}': {e}. Skipping.")
                continue
            if provider_obj is None:
                print(f"❓ Provider '{provider_name}' tidak ditemukan. Skipping.")
                continue

            # Create a task for each provider test
            task = asyncio.create_task(
                test_provider_async(provider_name, provider_obj, session, semaphore)
            )
            tasks.append(task)

        # Use tqdm.gather to show progress
        results = await tqdm.gather(*tasks, desc="🔍 Menguji Provider", unit="prov")
        # results list will contain the return value of test_provider_async or None if it failed early

    print("\n✅ Semua pengujian provider selesai. Memuat data akhir untuk ranking...")
    # Load final data after all updates are done
    final_data = load_results_sync()

    # Rank the final data
    ranked_data = rank_providers(final_data)  # Sync ranking function

    # Save the final ranked data
    await save_final_ranked_results(ranked_data)  # Use async save wrapper
    print(
        "\033[92m✨ Proses selesai. Database diperbarui secara real-time (async) & diranking di akhir.\033[0m"
    )


if __name__ == "__main__":
    # Check dependencies
    try:
        import inspect

        import aiohttp
        import requests
    except ImportError as e:
        print(
            f"Error: Dependency missing ({e}). Install required libraries (pip install aiohttp requests)."
        )
        exit(1)

    # Run the async main function
    try:
        asyncio.run(test_all_providers_async())
    except KeyboardInterrupt:
        print("\n🚫 Proses dihentikan oleh pengguna.")
    except Exception:
        print("\n💥 Terjadi error tidak terduga di proses utama:")
        traceback.print_exc()
