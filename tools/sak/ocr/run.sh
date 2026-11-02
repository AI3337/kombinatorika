#!/bin/zsh
# все страницы: PDF -> png 1600 (work/pages) -> ocr (work/ocr/pNNN.tsv)
cd "$(dirname $0)/.."
mkdir -p work/pages work/ocr
for p in $(seq 5 359); do
  f=$(printf "work/pages/p%03d.png" $p); o=$(printf "work/ocr/p%03d.tsv" $p)
  [ -f $f ] || OUT=work/pages python3 pdfpage.py $p 1600 >/dev/null
  [ -f $o ] || ocr/ocr $f $o
done
echo готово $(ls work/ocr | wc -l)
