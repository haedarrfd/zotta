import toml

output_file = ".streamlit/secrets.toml"

with open("key.json") as file_key:
    key_firebase = file_key.read()

config = {"textkey":key_firebase}

toml_config = toml.dumps(config)

with open(output_file, "w") as target:
    target.write(toml_config)