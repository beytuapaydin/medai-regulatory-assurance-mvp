# MedAI Assurance — Research MVP v1.0 / Release Candidate 1

**Kapsam:** MEDAI-PTBXL-MI-001 araştırma sisteminin mimarisi, geliştirme sonuçları, kanıt bağlantıları, açık riskleri ve NO_GO kararının **GitHub'a uygun dokümantasyon paketi**.

**Bu bir tam uygulama kaynağı değildir.** Mevcut Windows klasörlerindeki gerçek kod/modeller/veriler bu ZIP'e kopyalanmaz. Bu kasıtlıdır; kaynak kodu daha sonra ayrı bir gözden geçirme ve gizli veri taramasından geçirerek GitHub deposuna eklemeliyiz. Bu paket Fold 10 çalıştırıcısı sağlamaz.

## Kurulum

ZIP'i `Downloads` klasörüne kaydet; PowerShell'de:

```powershell
$ErrorActionPreference = 'Stop'
$docs = "$env:USERPROFILE\Documents"
$zip = "$env:USERPROFILE\Downloads\MedAI-Assurance-Research-MVP-v1.0-RC1.zip"
$dest = "$docs\MedAI-Assurance-Research-MVP-v1.0-RC1"
if (!(Test-Path -LiteralPath $zip)) { throw "ZIP bulunamadı: $zip" }
if (Test-Path -LiteralPath $dest) { throw "Klasör mevcut, üzerine yazılmayacak: $dest" }
Expand-Archive -LiteralPath $zip -DestinationPath $docs
python -m pytest -q "$dest\tests\test_release_evidence.py"
if ($LASTEXITCODE -ne 0) { throw 'RC tests failed' }
$out = "$docs\MedAI-RC1-Evidence-Verification.json"
if (Test-Path -LiteralPath $out) { throw "Var olan rapor korunuyor: $out" }
python -u "$dest\tools\verify_release_evidence.py" --docs $docs --output $out
if ($LASTEXITCODE -ne 0) { throw 'FAIL_CLOSED: Evidence mismatched' }
(Get-FileHash -LiteralPath $out -Algorithm SHA256).Hash
```

Beklenen: `ALL_REGISTERED_EVIDENCE_HASHES_MATCH`, `HOLDOUT AUTHORIZED: NO`, 15 kanıt dosyası. Doğrulama bunları yalnızca kullanıcı bilgisayarında gerçekten mevcutlarsa ve hash'ler tutuyorsa başarılı sayar. Geliştirme sonucu veya holdout yetkisi yaratmaz.

## MVP bitiş tanımı

- **RC1 şu an:** Geliştirme sonuçları ve denetim zinciri belgelenir, NO_GO korunur.
- **Research MVP v1.0 Final için:** Harici/bağımsız inceleme gerçek kayda alınmalı, holdout yetkisi ayrı karara bağlanmalı; Fold 10 yürütülürse sonuçlar değiştirilmeden yayımlanmalı; gerçek kod ve dokümantasyon son kontrollerden geçmeli.
- Fold 10 yetkisi gecikirse, **honest research prototype RC1** olarak yayınlanabilir; ancak final/holdout-validated diye sunulamaz.
