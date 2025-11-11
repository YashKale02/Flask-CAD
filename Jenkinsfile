pipeline {
    agent any

    stages {
        stage('1. Checkout Code') {
            steps {
                // This pulls your code from GitHub
                git url: 'https://github.com/YashKale02/Flask-CAD.git', branch: 'main'
            }
        }

        stage('2. Install Dependencies') {
            steps {
                // This runs the pip3 install command
                sh 'pip3 install flask pymongo python-dotenv waitress'
            }
        }

        stage('3. Deploy Application') {
            steps {
                script {
                    // This is the tricky part - we must stop the old server first
                    try {
                        // Find and kill the process using port 5000
                        sh 'kill $(lsof -t -i:5000)'
                    } catch (any) {
                        // This just means the server wasn't running, which is fine
                        echo 'Flask app was not running, starting new one...'
                    }

                    // Start the new server in the background
                    sh 'nohup python3 app.py &'
                }
            }
        }
    }
}