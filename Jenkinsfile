pipeline {
    agent any

    environment {
        DOCKERHUB_USER = 'bmelnikov02'
        TAG = "${env.BUILD_NUMBER}"
        STACK = 'pm'
    }

    triggers {
        pollSCM('H/2 * * * *')
    }

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    stages {
        stage('Build') {
            steps {
                sh '''
                    for service in simulator collector predictor; do
                        docker build -t "$DOCKERHUB_USER/pm-$service:$TAG" "./$service"
                    done
                '''
            }
        }

        stage('Test') {
            steps {
                sh 'docker run --rm "$DOCKERHUB_USER/pm-predictor:$TAG" python -m pytest -v'
            }
        }

        stage('Push') {
            steps {
                withCredentials([usernamePassword(credentialsId: 'dockerhub', usernameVariable: 'HUB_USER', passwordVariable: 'HUB_TOKEN')]) {
                    sh '''
                        echo "$HUB_TOKEN" | docker login -u "$HUB_USER" --password-stdin
                        for service in simulator collector predictor; do
                            docker push "$DOCKERHUB_USER/pm-$service:$TAG"
                        done
                    '''
                }
            }
        }

                stage('Deploy') {
            steps {
                withCredentials([file(credentialsId: 'pm-env', variable: 'ENV_FILE')]) {
                    sh '''
                        set +x
                        sed 's/\\r$//' "$ENV_FILE" > deploy.env
                        set -a
                        . ./deploy.env
                        set +a
                        rm -f deploy.env
                        export TAG="$BUILD_NUMBER"
                        echo "Деплой стека $STACK, версия $TAG"
                        docker stack deploy --detach=false -c docker-stack.yml "$STACK"
                    '''
                }
            }
        }

        stage('Smoke test') {
            steps {
                sh '''
                    for i in $(seq 1 20); do
                        if curl -fsS http://manager/ml/health && curl -fsS http://manager/api/health; then
                            echo "Система отвечает"
                            exit 0
                        fi
                        sleep 6
                    done
                    echo "Система не отвечает после деплоя"
                    exit 1
                '''
            }
        }
    }

    post {
        always {
            sh 'docker logout || true'
        }
        success {
            echo "Версия ${env.TAG} развёрнута в кластере"
        }
        failure {
            echo "Сборка ${env.BUILD_NUMBER} завершилась ошибкой"
        }
    }
}