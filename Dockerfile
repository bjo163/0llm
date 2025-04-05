FROM selenium/node-chrome

ARG G4F_VERSION
ENV G4F_VERSION $G4F_VERSION

ENV SE_SCREEN_WIDTH 1850
ENV G4F_DIR /app
# ENV G4F_LOGIN_URL http://localhost:7900/?autoconnect=1&resize=scale&password=secret
ENV G4F_LOGIN_URL=http://localhost:7900/?auto-login=true

# --- Tetap sebagai root untuk instalasi awal ---
USER root

#  If docker compose, install git
RUN if [ "$G4F_VERSION" = "" ] ; then \
  apt-get -qqy update && \
  apt-get -qqy install git \
  ; fi

# Install Python3, pip, remove OpenJDK 11, clean up
RUN apt-get -qqy update \
  && apt-get -qqy upgrade \
  && apt-get -qyy autoremove \
  && apt-get -qqy install python3 python-is-python3 pip \
  && apt-get -qyy remove openjdk-11-jre-headless \
  && apt-get -qyy autoremove \
  && apt-get -qyy clean \
  && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

# Update entrypoint (supervisor conf)
COPY docker/supervisor.conf /etc/supervisor/conf.d/selenium.conf
COPY docker/supervisor-api.conf /etc/supervisor/conf.d/api.conf

# Change background image
COPY docker/background.png /usr/share/images/fluxbox/ubuntu-light.png

# --- Lakukan operasi file yang memerlukan root SEBELUM berganti user ---

# Set the working directory in the container.
# Menetapkan WORKDIR lebih awal agar path relatif lebih mudah
WORKDIR $G4F_DIR

# 1. Copy requirements.txt (sebelumnya dilakukan setelah berganti user)
COPY requirements.txt $G4F_DIR/

# 2. Copy kode aplikasi (sebelumnya menggunakan ADD --chown)
COPY g4f $G4F_DIR/g4f/

# 3. BUAT DIREKTORI LOGS dan SET IZIN (Baru Ditambahkan)
#    Kita buat direktori SEKARANG saat masih root,
#    lalu berikan kepemilikan ke user selenium (SEL_UID/SEL_GID)
RUN mkdir -p $G4F_DIR/logs && chown -R ${SEL_UID}:${SEL_GID} $G4F_DIR/logs

# 4. Fix permissions (seperti sebelumnya, pastikan dilakukan *setelah* file dibuat/dicopy)
RUN chown -R "${SEL_UID}:${SEL_GID}" "$HOME" "$G4F_DIR"

# --- SEKARANG baru ganti user ---
USER $SEL_UID

# Upgrade pip for the latest features and install the project's Python dependencies.
# Dilakukan sebagai SEL_UID
RUN pip install --break-system-packages --upgrade pip \
  && pip install --break-system-packages -r requirements.txt

# Expose ports
EXPOSE 1337 8080 7900

# CMD atau ENTRYPOINT Anda akan dijalankan sebagai SEL_UID
# Jika Anda menggunakan supervisord, pastikan proses di dalam conf
# (seperti g4f-api) juga berjalan sebagai user yang benar jika perlu,
# atau pastikan direktori yang ditulisnya memiliki izin yang sesuai.
# Contoh (jika supervisord.conf tidak menentukan user):
# CMD ["supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]