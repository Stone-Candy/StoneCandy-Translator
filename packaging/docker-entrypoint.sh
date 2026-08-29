#!/bin/bash
set -e

# Restore default examples if directory is empty
if [ -d "/app/default_examples" ] && [ -d "/app/examples" ]; then
    if [ -z "$(ls -A /app/examples)" ]; then
        echo "Initializing empty examples directory..."
        cp -r /app/default_examples/* /app/examples/ || true
    fi
fi

# Restore default fonts if directory is empty
if [ -d "/app/default_fonts" ] && [ -d "/app/fonts" ]; then
    if [ -z "$(ls -A /app/fonts)" ]; then
        echo "Initializing empty fonts directory..."
        cp -r /app/default_fonts/* /app/fonts/ || true
    fi
fi

# Restore default dict if directory is empty
if [ -d "/app/default_dict" ] && [ -d "/app/dict" ]; then
    if [ -z "$(ls -A /app/dict)" ]; then
        echo "Initializing empty dict directory..."
        cp -r /app/default_dict/* /app/dict/ || true
    fi
fi

# Restore default server data if directory is empty
if [ -d "/app/default_server_data" ] && [ -d "/app/manga_translator/server/data" ]; then
    if [ -z "$(ls -A /app/manga_translator/server/data)" ]; then
        echo "Initializing empty server data directory..."
        cp -r /app/default_server_data/* /app/manga_translator/server/data/ || true
    fi
fi

# Execute the main command
exec "$@"
