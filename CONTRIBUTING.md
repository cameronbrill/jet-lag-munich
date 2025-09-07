## Environment set up

1. Clone the repository:

```bash
git clone <repository-url>
cd crypto-algo-trader
```

2. Install [mise](https://mise.jdx.dev/)

&nbsp; &nbsp; &nbsp; &nbsp; a. Make sure you've configured it to [work with IDEs](https://mise.jdx.dev/ide-integration.html#adding-shims-to-path-default-shell)

3. Install dependencies

```bash
mise install
mise setup
```

4. Install recommended VSCode extensions

That's it! Your environment is set up :)

### Run code quality checks:

```bash
# Format code
mise format

# Check linting
mise lint

# Type checking
mise typecheck

# Run tests
mise test
```
