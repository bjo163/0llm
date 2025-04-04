import re
import json
import os
import time
import datetime
from g4f import ChatCompletion
from g4f.Provider import ProviderUtils
from g4f.client import Client 
from tqdm import tqdm

client = Client(provider=ProviderUtils.get_provider())
db_path = "provider_results.json"

def load_results():
    if os.path.exists(db_path):
        with open(db_path, "r") as f:
            return json.load(f)
    return []

def save_result(result):
    data = load_results()
    data.append(result)
    with open(db_path, "w") as f:
        json.dump(data, f, indent=2)

ADVICE_MAP = {
    "✅ Working": "Provider stabil dan tidak membutuhkan autentikasi. Siap digunakan produksi.",
    "⏳ Slow Response": "Provider lambat merespons. Pertimbangkan untuk dipakai hanya untuk task non-realtime.",
    "⚠️ Unstable": "Provider tidak stabil. Gunakan fallback atau pertimbangkan alternatif.",
    "🔒 Needs Auth": "Provider membutuhkan autentikasi. Pastikan sudah di-setup token/kunci dengan benar.",
    "❌ Fallback Failed": "Fallback model gagal juga. Cek ketersediaan API atau endpoint bermasalah.",
    "❌ Not Working": "Gagal total. Coba cek jaringan, endpoint, atau mungkin provider deprecated.",
    "❓ Unknown": "Status tidak diketahui. Perlu dicek manual atau debug log lebih lanjut."
}

def generate_advice(status, error=None, needs_auth=False):
    base = ADVICE_MAP.get(status, ADVICE_MAP["❓ Unknown"])
    if status == "❌ Not Working" and error:
        base += f"\nError: {error}"
    return base

def evaluate_status_from_logs(logs, needs_auth=False):
    total = len(logs)
    if total == 0:
        return "❓ Unknown"

    successes = sum(1 for log in logs if log["success"])
    success_rate = successes / total
    response_times = [log["response_time"] for log in logs if log.get("response_time") is not None]
    avg_response = sum(response_times) / len(response_times) if response_times else None

    rules = [
        (needs_auth and success_rate > 0.5, "🔒 Needs Auth"),
        (success_rate <= 0.5, "❌ Not Working"),
        (success_rate < 0.9, "⚠️ Unstable"),
        (avg_response and avg_response > 3, "⏳ Slow Response"),
    ]

    for condition, status in rules:
        if condition:
            return status

    return "✅ Working"

# ✅ Fungsi baru: Minta solusi AI
def query_openai_solution(result):
    try:
        prompt = (
            f"Saya menguji sebuah provider API untuk LLM. Berikut detail hasil uji:\n\n"
            f"📌 Provider: {result['provider']}\n"
            f"🤖 Model: {result['model']}\n"
            f"📊 Status: {result['status']}\n"
            f"✅ Success: {'Ya' if result['success'] else 'Tidak'}\n"
            f"🔁 Fallback: {'Ya' if result['fallback'] else 'Tidak'}\n"
            f"🕒 Response Time: {result.get('response_time', 'N/A')} detik\n"
            f"📤 Request Parameters: model=gpt-3.5-turbo, message='hello', provider={result['provider']}\n"
            f"⚠️ Error: {result['error'] or 'Tidak ada'}\n\n"
            f"Tolong berikan analisa kemungkinan penyebab dan solusi teknis langkah demi langkah (maksimal 5 langkah)."
        )
        
        completion = client.chat.completions.create(
            
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Kamu adalah AI engineer yang membantu troubleshooting API LLM."},
                {"role": "user", "content": prompt}
            ],
            web_search = False,
            temperature=0.4,
            max_tokens=500,
        )
        return completion['choices'][0]['message']['content'].strip()
    except Exception as e:
        return f"Gagal mengambil solusi dari AI: {e}"

def calculate_score(success, response_time, fallback, status):
    score = 0
    if success:
        score += 50
        if response_time is not None:
            if response_time < 1:
                score += 30
            elif response_time < 3:
                score += 20
            elif response_time < 5:
                score += 10
        if status == "✅ Working":
            score += 20
        elif status == "⚠️ Unstable":
            score += 5
        elif status == "⏳ Slow Response":
            score -= 5
    else:
        score += 10  # masih dapat nilai dasar

    if fallback:
        score -= 10

    return max(1, min(100, score))

def rank_providers():
    print("\n📊 Mulai proses ranking provider...")

    all_results = load_results()
    latest_by_provider = {}
    
    print(f"📦 Memuat {len(all_results)} hasil pengujian sebelumnya...")

    # Ambil hasil terbaru per provider
    for res in all_results:
        latest_by_provider[res["provider"]] = res

    print(f"📌 Menemukan {len(latest_by_provider)} provider unik untuk diranking.\n")

    # Hitung skor dan simpan di result
    for provider, res in latest_by_provider.items():
        print(f"🔍 Menghitung skor untuk: {provider}")
        score = calculate_score(
            success=res.get("success", False),
            response_time=res.get("response_time", None),
            fallback=res.get("fallback", False),
            status=res.get("status", "❓ Unknown")
        )
        print(f"🎯 Skor: {score}")
        res["score"] = score

    # Urutkan dan beri peringkat
    sorted_providers = sorted(latest_by_provider.values(), key=lambda r: r["score"], reverse=True)
    for rank, res in enumerate(sorted_providers, 1):
        res["rank"] = rank
        print(f"🏅 {rank}. {res['provider']} (Skor: {res['score']})")

    # Simpan kembali ke file
    with open(db_path, "w") as f:
        json.dump(sorted_providers, f, indent=2)

    print(f"\033[92m✅ Ranking berhasil diperbarui...\033[0m")



def test_provider(provider, previous_logs):
    print(f"\n🧪 Mulai pengujian untuk provider: {provider}")
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    provider_obj = ProviderUtils.convert.get(provider)
    if provider_obj is None:
        print("❓", provider, "not found in ProviderUtils.")
        return

    start_time = time.time()
    
    try:
        print("📤 Mengirim request ke model...")
        response = ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "hello"}],
            provider=provider_obj
        )
        duration = round(time.time() - start_time, 2)
        print("✅ Respons diterima. Menghitung skor dan status...")
        result = {
            "timestamp": now,
            "provider": provider,
            "status": None,
            "model": "gpt-3.5-turbo",
            "fallback": False,
            "success": True,
            "response": str(response),
            "response_time": duration,
            "error": None,
            "advice": None
        }
        previous_logs.append(result)
        result["status"] = evaluate_status_from_logs(previous_logs, provider_obj.needs_auth)
        result["advice"] = generate_advice(result["status"])
        result["ai_solution"] = query_openai_solution(result)  # ✅ Tambahan di sini
        result["score"] = calculate_score(
    success=result["success"],
    response_time=result.get("response_time", None),
    fallback=result.get("fallback", False),
    status=result["status"]
)
        print(f"🎯 Skor awal: {result['score']}")
        print("✅", provider, result["status"])
        save_result(result)
        return

    except Exception as e:
        duration = round(time.time() - start_time, 2)
        err_str = str(e)
        fallback_model = None

        if "Model is not supported" in err_str:
            match = re.search(r"Valid models: (\[.*?\])", err_str)
            if match:
                valid_models = eval(match.group(1))
                if valid_models:
                    fallback_model = valid_models[0]
                    try:
                        print("♻️ Menggunakan model fallback:", fallback_model)
                        response = ChatCompletion.create(
                            model=fallback_model,
                            messages=[{"role": "user", "content": "hello"}],
                            provider=provider_obj
                        )
                        duration = round(time.time() - start_time, 2)
                        result = {
                            "timestamp": now,
                            "provider": provider,
                            "status": None,
                            "model": fallback_model,
                            "fallback": True,
                            "success": True,
                            "response": str(response),
                            "response_time": duration,
                            "error": None,
                            "advice": None
                        }
                        previous_logs.append(result)
                        result["status"] = evaluate_status_from_logs(previous_logs, provider_obj.needs_auth)
                        result["advice"] = generate_advice(result["status"])
                        result["ai_solution"] = query_openai_solution(result)
                        result["score"] = calculate_score(
    success=result["success"],
    response_time=result.get("response_time", None),
    fallback=result.get("fallback", False),
    status=result["status"]
)
                        print(f"🎯 Skor fallback: {result['score']}")
                        print("✅", provider, "with fallback:", fallback_model, result["status"])
                        save_result(result)
                        return
                    except Exception as fallback_error:
                        result = {
                            "timestamp": now,
                            "provider": provider,
                            "status": "❌ Fallback Failed",
                            "model": fallback_model,
                            "fallback": True,
                            "success": False,
                            "response": None,
                            "response_time": duration,
                            "error": str(fallback_error),
                            "advice": generate_advice("❌ Fallback Failed", str(fallback_error)),
                            "ai_solution": query_openai_solution({
                                "provider": provider,
                                "model": fallback_model,
                                "status": "❌ Fallback Failed",
                                "fallback": True,
                                "success": False,
                                "response_time": duration,
                                "error": str(fallback_error)
                            })
                            
                        }
                        print("❌", provider, "fallback failed")
                        save_result(result)
                        return

        result = {
            "timestamp": now,
            "provider": provider,
            "status": None,
            "model": "gpt-3.5-turbo",
            "fallback": False,
            "success": False,
            "response": None,
            "response_time": duration,
            "error": err_str,
            "advice": None
        }
        previous_logs.append(result)
        result["status"] = evaluate_status_from_logs(previous_logs, provider_obj.needs_auth)
        result["advice"] = generate_advice(result["status"], err_str, provider_obj.needs_auth)
        result["ai_solution"] = query_openai_solution(result)
        result["score"] = calculate_score(
    success=result["success"],
    response_time=result.get("response_time", None),
    fallback=result.get("fallback", False),
    status=result["status"]
)

        print("❌", provider, result["status"])
        save_result(result)

def test_all_providers():
    print("🚀 Testing all G4F providers...\n")

    existing = load_results()
    grouped_logs = {}
    for log in existing:
        grouped_logs.setdefault(log["provider"], []).append(log)

    all_providers = list(ProviderUtils.convert.keys())

    for provider in tqdm(all_providers, desc="🔍 Testing providers", ncols=100):
        logs = grouped_logs.get(provider, [])
        result = test_provider(provider, logs)

        # Log hasil tes provider tetap ditampilkan
        if result:
            msg = f"✅ {provider} | status: {result.get('status')} | time: {result.get('response_time')}s"
        else:
            msg = f"❌ {provider} gagal dites."

        tqdm.write(msg)
        time.sleep(0.2)  # Biar kerasa progress-nya

    print("\n✅ Semua provider selesai dites.")
    rank_providers()
if __name__ == "__main__":
    test_all_providers()
