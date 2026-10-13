FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive \
    ANDROID_HOME=/opt/android-sdk \
    ANDROID_SDK_ROOT=/opt/android-sdk \
    AOSP_IMAGE_DIR=/opt/aosp-image \
    ANDROID_AVD_HOME=/data/avd \
    DISPLAY=:0 \
    PATH=/opt/android-sdk/platform-tools:/opt/android-sdk/emulator:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl unzip openjdk-17-jre-headless python3 python3-pip \
    xvfb openbox x11vnc x11-utils websockify novnc \
    libgl1 libegl1 libnss3 libx11-6 libx11-xcb1 libxcb1 libxcb-render0 libxcb-shape0 \
    libxcb-xfixes0 libxcb-randr0 libxcb-xinerama0 libxcb-cursor0 libxcb-icccm4 \
    libxcb-keysyms1 libxcb-util1 libxcomposite1 libxcursor1 libxext6 libxi6 \
    libxtst6 libxrandr2 libxrender1 libxfixes3 libxkbcommon0 libxkbcommon-x11-0 \
    libasound2 libpulse0 libdbus-1-3 libfontconfig1 libvulkan1 libgcc-s1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

# Google Android SDK command-line tools; the Android 12 system image itself is built from AOSP.
ARG CMDLINE_TOOLS_REV=11076708
RUN mkdir -p /opt/android-sdk/cmdline-tools \
    && curl -fsSL "https://dl.google.com/android/repository/commandlinetools-linux-${CMDLINE_TOOLS_REV}_latest.zip" -o /tmp/cmdline-tools.zip \
    && mkdir -p /tmp/cmdline-tools-unpack \
    && unzip -q /tmp/cmdline-tools.zip -d /tmp/cmdline-tools-unpack \
    && mv /tmp/cmdline-tools-unpack/cmdline-tools /opt/android-sdk/cmdline-tools/latest \
    && rm -rf /tmp/cmdline-tools.zip /tmp/cmdline-tools-unpack \
    && yes | /opt/android-sdk/cmdline-tools/latest/bin/sdkmanager --sdk_root=/opt/android-sdk --licenses >/dev/null

RUN yes | /opt/android-sdk/cmdline-tools/latest/bin/sdkmanager --sdk_root=/opt/android-sdk \
      "platform-tools" "emulator" "platforms;android-31" >/dev/null

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r /app/requirements.txt
COPY app.py /app/app.py
RUN mkdir -p /data/avd /data/home /opt/aosp-image
EXPOSE 8000 6080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
