FROM python:3.9-slim AS epanet-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
	build-essential \
	cmake \
	git \
	ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
	git clone --depth 1 --branch v2.2 https://github.com/OpenWaterAnalytics/EPANET.git /tmp/epanet; \
	cmake -S /tmp/epanet -B /tmp/epanet/build -DBUILD_SHARED_LIBS=ON -DCMAKE_BUILD_TYPE=Release; \
	cmake --build /tmp/epanet/build -j"$(nproc)"; \
	EPANET_SO=$(find /tmp/epanet/build -type f -name 'libepanet*.so*' | head -n 1); \
	cp "$EPANET_SO" /tmp/libepanet2_2.so

FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=epanet-builder /tmp/libepanet2_2.so /tmp/libepanet2_2.so

RUN set -eux; \
	EPYT_LIB_DIR=$(python -c "import epyt, os; print(os.path.join(os.path.dirname(epyt.__file__), 'libraries', 'glnx'))"); \
	cp /tmp/libepanet2_2.so "$EPYT_LIB_DIR/libepanet2_2.so"; \
	ln -sf "$EPYT_LIB_DIR/libepanet2_2.so" "$EPYT_LIB_DIR/libepanet.so"; \
	ln -sf "$EPYT_LIB_DIR/libepanet2_2.so" "$EPYT_LIB_DIR/libepanet2.so"; \
	ls -l "$EPYT_LIB_DIR"

COPY main.py .

CMD ["python", "main.py"]