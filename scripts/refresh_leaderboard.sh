#!/bin/bash
# Refresh the G-Pose leaderboard by calling the bot API
curl -s -X POST http://192.168.0.132:8443/gpose/leaderboard \
  -H "X-API-Key: elfbingo" \
  -H "Content-Type: application/json" \
  -o /dev/null -w "LB refresh: %{http_code} (%{time_total}s)\n"