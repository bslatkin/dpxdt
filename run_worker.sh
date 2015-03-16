 #!/bin/bash

./dpxdt/tools/run_server.py \
    --enable_queue_workers \
    --release_server_prefix=http://localhost:5000/api \
    --queue_server_prefix=http://localhost:5000/api/work_queue \
    --verbose \
    "$@"
