#!/bin/bash

count=$#

if [ "$count" -eq 0 ]; then
    echo "Количество аргументов: 0"
    echo "Среднее арифметическое вычислить нельзя"
    exit 1
fi

sum=0

for number in "$@"
do
    sum=$((sum + number))
done

average=$(awk -v sum="$sum" -v count="$count" 'BEGIN { printf "%.2f", sum / count }')

echo "Количество аргументов: $count"
echo "Среднее арифметическое: $average"