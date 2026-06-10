# user-service (FOSSA POC)

Spring Boot 3.3 + Java 21 microservice (Gradle) with intentional FOSSA findings.

## Intentional findings (for demo)

### Security vulnerabilities

| Dependency | Version | Example CVE | Fix |
|------------|---------|-------------|-----|
| commons-text | 1.9 | CVE-2022-42889 | 1.10.0+ |
| snakeyaml | 1.33 | CVE-2022-14798 | 2.0+ |
| log4j-core | 2.14.1 | CVE-2021-44228 (Log4Shell) | 2.17.2+ |
| commons-collections | 3.2.1 | CVE-2015-7501 | 3.2.2+ |
| json-smart | 2.3 | CVE-2021-27568 | 2.4.11+ |
| commons-io | 2.6 | CVE-2021-29425 | 2.7+ |
| commons-fileupload | 1.4 | CVE-2023-24998 | 1.5+ |

### License policy violations

| Dependency | Version | License | Mitigation |
|------------|---------|---------|------------|
| org.json:json | 20210307 | JSON License | Remove (use Jackson from Spring Boot) |
| com.mysql:mysql-connector-j | 8.0.33 | CVE-2023-22102 | Bump to 8.2.0+ (Maven Central) |

**Do not deploy to production.**

## Run locally

```bash
./gradlew test
./gradlew bootRun
curl http://localhost:8081/health
```

## FOSSA scan

```bash
fossa analyze
fossa test
```

See [../../docs/FOSSA_SETUP.md](../../docs/FOSSA_SETUP.md).
