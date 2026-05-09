---
tags: [project-study, minegold-brave]
---

# Containerization and Deployment Strategy

The project uses a multi-stage `Dockerfile` to create a reproducible build and deployment environment based on `ubuntu:24.04`. This approach encapsulates all dependencies and system configurations, ensuring consistency across different development and CI/CD environments.

## Key Components of the Docker Environment

The Docker image is built with a specific set of tools required for developing and deploying on the Internet Computer:

- **Base Image**: `ubuntu:24.04`
- **Node.js**: Version `20.x` is installed via NodeSource, providing the JavaScript runtime.
- **Package Management**: `pnpm` is installed globally for efficient Node.js package management.
- **IC Tooling**:
    - `ic-mops`: The Motoko package manager.
    - `icp-cli`: The command-line interface for interacting with the Internet Computer.
    - `motoko`: The Motoko compiler (`v1.2.0`) and its core/base libraries are manually installed from GitHub releases.

### Environment Configuration

The image is configured to run as a non-root `ubuntu` user for enhanced security. Several environment variables are set to configure the paths for the Motoko compiler and its libraries:

```dockerfile
USER ubuntu
WORKDIR /home/ubuntu
ENV HOME=/home/ubuntu

# ... PATH setup ...

# Set Motoko environment variables for deploy.sh and other scripts
ENV MOC_PATH="/home/ubuntu/.motoko/moc/1.2.0/bin/moc"
ENV MOTOKO_CORE="/home/ubuntu/.motoko/core/moc-1.2.0"
ENV MOTOKO_BASE="/home/ubuntu/.motoko/base/SKIP"
```

## Deployment Execution

The container's primary purpose is to execute the deployment script. The project files are copied into the `/workdir` directory, and the `deploy.sh` script is set as the container's entrypoint.

```dockerfile
WORKDIR /workdir

# Copy project files into the image
COPY --chown=ubuntu:ubuntu . /workdir/

RUN chmod +x /workdir/deploy.sh

ENTRYPOINT ["/workdir/deploy.sh"]
```

This design makes the container an executable artifact for deployment. Running the container will automatically trigger the project's deployment process as defined in `deploy.sh`, which is covered in more detail in the [[developer-scripts-and-launch-automation]] note.