#!/bin/bash
# File: dev-docker-build.sh
# Description: Rebuild and restart docker-compose dev environment with numbered logs, checks, commit, and push.

# --- Konfigurasi ---
set -e # Keluar segera jika sebuah perintah keluar dengan status bukan nol
COMPOSE_FILE="docker-compose.dev.yml"
GIT_BRANCH="main" # Branch yang akan di-push
REMOTE_1="origin"
REMOTE_2="space"
WAIT_SECONDS=5 # Waktu (detik) untuk menunggu container stabil sebelum pemeriksaan
LOG_TAIL_LINES=50 # Jumlah baris log terakhir yang ditampilkan di akhir

# --- Variabel Internal ---
STEP_COUNT=0 # Penghitung langkah untuk logging

# --- Fungsi Bantuan ---

# Fungsi untuk mencetak log langkah bernomor
log_step() {
    STEP_COUNT=$((STEP_COUNT + 1))
    echo -e "\n[STEP ${STEP_COUNT}] $1" # Menggunakan -e untuk interpretasi \n
}

# Fungsi untuk menjalankan perintah dengan penanganan error
run_command() {
    echo "   🚀 Executing: $@"
    "$@" # Menjalankan perintah
    local status=$?
    if [ $status -ne 0 ]; then
        echo "   ❌ ERROR: Command failed with status $status: $*" >&2
        exit $status
    fi
    echo "   ✅ Command successful: $*"
}

# Fungsi untuk memeriksa apakah container berjalan dan dapat diakses
check_container_exec() {
    local full_container_name=$1 # Docker Compose biasanya menambahkan prefix
    echo "   🔍 Checking accessibility for container: ${full_container_name}..."

    # Coba eksekusi perintah sederhana di dalam container
    if docker exec "${full_container_name}" sh -c "exit 0" > /dev/null 2>&1; then
        echo "   ✅ Container ${full_container_name} is accessible."
        return 0 # Sukses
    else
        # Coba cek apakah container setidaknya running jika exec gagal
        if docker ps --filter "name=^/${full_container_name}$" --filter "status=running" --quiet > /dev/null; then
             echo "   ⚠️ Container ${full_container_name} is RUNNING but not accessible via 'docker exec'. Might still be initializing."
             return 1 # Gagal parsial (berjalan tapi tidak bisa di-exec)
        else
             echo "   ❌ Container ${full_container_name} is NOT RUNNING or not found."
             return 1 # Gagal total
        fi
    fi
}

# Fungsi untuk melakukan commit perubahan ke Git (hanya jika ada perubahan)
commit_changes() {
    log_step "Checking for Git changes..."
    # Cek apakah ada perubahan yang belum di-commit (staged atau unstaged)
    if [[ -z $(git status --porcelain) ]]; then
        echo "   ℹ️ No changes detected in the working directory. Skipping commit."
        return 0 # Tidak ada yang perlu di-commit
    fi

    local commit_message="Automated commit for ${COMPOSE_FILE} rebuild on $(date +'%Y-%m-%d %H:%M:%S %Z')"
    echo "   📝 Found changes. Staging and committing with message: '${commit_message}'"
    run_command git add .
    run_command git commit -m "$commit_message"
}

# --- Alur Utama Skrip ---

log_step "Stopping existing containers defined in ${COMPOSE_FILE} (if any)..."
# Menggunakan 'docker compose down' tanpa error jika tidak ada container (opsi --remove-orphans bisa berguna)
# Menekan output jika tidak ada yang dihentikan untuk kejelasan
docker compose -f "${COMPOSE_FILE}" down --remove-orphans || true # || true agar tidak error jika tidak ada yg berjalan

log_step "Rebuilding images and starting containers in detached mode from ${COMPOSE_FILE}..."
run_command docker compose -f "${COMPOSE_FILE}" up --build -d

log_step "Waiting ${WAIT_SECONDS} seconds for containers to stabilize..."
sleep "${WAIT_SECONDS}"

log_step "Checking container status and accessibility..."
services=$(docker compose -f "${COMPOSE_FILE}" config --services)
accessible_services=()
inaccessible_services=()

# Mendapatkan nama project dari Docker Compose (biasanya nama direktori)
project_name=$(docker compose -f "${COMPOSE_FILE}" config --format json | grep '"name":' | sed 's/.*"name": "\(.*\)",/\1/')
if [ -z "$project_name" ]; then
    echo "   ⚠️ Could not determine docker compose project name. Using service name only for checks (might be less accurate)."
fi


for service in $services; do
    # Mencoba menebak nama container (biasanya: projectname-service-1)
    # Ini mungkin perlu disesuaikan jika Anda memiliki konfigurasi nama container kustom
    container_name_guess="${project_name}-${service}-1"

    # Alternatif: Coba cari container berdasarkan label service compose
    container_id=$(docker ps -q --filter "label=com.docker.compose.service=${service}" --filter "label=com.docker.compose.project=${project_name}")

    if [ -n "$container_id" ]; then
        # Dapatkan nama dari ID jika ditemukan
         actual_container_name=$(docker inspect --format '{{.Name}}' $container_id | sed 's/^\///') # Hapus '/' di awal
         echo "   ℹ️ Found container for service '${service}': ${actual_container_name}"
         if check_container_exec "${actual_container_name}"; then
             accessible_services+=("${service} (${actual_container_name})")
         else
             inaccessible_services+=("${service} (${actual_container_name})")
         fi
    else
        echo "   ⚠️ Could not find a running container for service '${service}' based on labels. Trying guessed name '${container_name_guess}'."
         # Coba tebakan jika label tidak ditemukan
         if check_container_exec "${container_name_guess}"; then
             accessible_services+=("${service} (${container_name_guess})")
         else
             inaccessible_services+=("${service} (${container_name_guess})")
         fi
    fi
done

echo "" # Baris baru untuk pemisah
echo "   --- Accessibility Summary ---"
if [ ${#accessible_services[@]} -gt 0 ]; then
    echo "   ✅ Accessible Services:"
    for svc in "${accessible_services[@]}"; do echo "      - $svc"; done
else
    echo "   ℹ️ No services were confirmed as accessible via 'docker exec'."
fi
if [ ${#inaccessible_services[@]} -gt 0 ]; then
    echo "   ❌ Inaccessible/Problematic Services:"
    for svc in "${inaccessible_services[@]}"; do echo "      - $svc"; done
else
    echo "   ℹ️ All checked services seem accessible or running."
fi
echo "   ---------------------------"


# (Opsional) Tampilkan log terakhir dari semua container setelah semua selesai
log_step "Showing last ${LOG_TAIL_LINES} lines of logs from all containers..."
run_command docker compose -f "${COMPOSE_FILE}" logs --tail="${LOG_TAIL_LINES}" --no-log-prefix

# Lakukan commit perubahan (jika ada)
commit_changes # Fungsi ini sudah memiliki log_step sendiri

log_step "Pushing changes to remotes..."
echo "   ℹ️ Pushing branch '${GIT_BRANCH}' to remote '${REMOTE_1}'..."
run_command git push "${REMOTE_1}" "${GIT_BRANCH}"
# PERINGATAN: --force dihilangkan karena berisiko. Gunakan hanya jika Anda TAHU apa yang Anda lakukan.
# Jika Anda benar-benar perlu, gunakan 'git push --force-with-lease ${REMOTE_1} ${GIT_BRANCH}' sebagai alternatif yang lebih aman.
# run_command git push --force ${REMOTE_1} ${GIT_BRANCH} # <-- Versi asli yang berisiko

echo "   ℹ️ Pushing branch '${GIT_BRANCH}' to remote '${REMOTE_2}'..."
run_command git push "${REMOTE_2}" "${GIT_BRANCH}"
# Sama seperti di atas, --force dihilangkan.
# run_command git push --force ${REMOTE_2} ${GIT_BRANCH} # <-- Versi asli yang berisiko

log_step "Deployment script finished successfully!"
echo "✅ Orchestration complete."
exit 0