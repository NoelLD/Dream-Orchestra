# Simulation service: MuJoCo YAM scene (Dream Labs example), Dream-1 control loop, FastAPI on :3001.
# Headless rendering via Mesa (EGL, software); optional browser view of a virtual display via noVNC on :6080.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DREAM_LOG=off \
    MUJOCO_GL=egl \
    HOME=/tmp \
    DREAM_YAM_EXAMPLE=/opt/dreamlabs/dream_library/examples/yam_mujoco \
    SIM_DATA_DIR=/data

RUN apt-get update && apt-get install -y --no-install-recommends \
        libegl1 libgl1 libgles2 libgl1-mesa-dri libglx-mesa0 libosmesa6 ffmpeg git ca-certificates \
        xvfb x11vnc novnc websockify fluxbox procps \
    && rm -rf /var/lib/apt/lists/*

# Dream Labs open-source example scene, pinned to the commit the code was tested against.
ARG DREAMLABS_COMMIT=ba8ad9850dd2e783b3c10fc079b0b5f78d7df441
RUN git init -q /opt/dreamlabs \
    && git -C /opt/dreamlabs remote add origin https://github.com/dreamlabs-co/dreamlabs \
    && git -C /opt/dreamlabs sparse-checkout set dream_library/examples/yam_mujoco \
    && git -C /opt/dreamlabs fetch -q --depth 1 origin "$DREAMLABS_COMMIT" \
    && git -C /opt/dreamlabs checkout -q FETCH_HEAD \
    && rm -rf /opt/dreamlabs/.git

WORKDIR /app
COPY src/Simulation/requirements.txt .
RUN python -m pip install --no-cache-dir --no-compile -r requirements.txt
COPY src/Simulation/ ./

RUN mkdir -p /data && chown 10001:10001 /data
USER 10001:10001
EXPOSE 3001 6080
CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "/app", "--host", "0.0.0.0", "--port", "3001"]
