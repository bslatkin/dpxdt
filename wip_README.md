TODO: Work in progress


------


create secrets.py with these values:

go to the API console and update config with your own oauth scopes:

generate the db
create database test;

create a build

create an API key

make yourself and your api key superusers

select * from user;
update user set superuser = 1 where user.id = 'foo';
select * from api_key;
update api_key set superuser = 1 where id = 'foo';



app engine specific stuff

go here to provision cloudsql

connect to your sql instance this way

google_sql.sh dpxdt-cloud:test


---

site diff


Example local usage:

./site_diff.py \
    --phantomjs_binary=path/to/phantomjs-1.8.1-macosx/bin/phantomjs \
    --phantomjs_script=path/to/client/capture.js \
    --pdiff_binary=path/to/pdiff/perceptualdiff \
    --output_dir=path/to/your/output \
    http://www.example.com/my/website/here


Example usage with API server:

./site_diff.py \
    --phantomjs_binary=path/to/phantomjs-1.8.1-macosx/bin/phantomjs \
    --phantomjs_script=path/to/client/capture.js \
    --pdiff_binary=path/to/pdiff/perceptualdiff \
    --output_dir=path/to/your/output \
    --upload_build_id=1234 \
    http://www.example.com/my/website/here



    # To run a very simple site diff when the local server is runnin, use:
    #
    # ./run_site_diff.sh \
    #   --upload_build_id=2 \
    #   --upload_release_name='blue' \
    #   http://localhost:5000/static/dummy_page1.html


    -------

    Testing locally

    ./run_site_diff.sh \
      --upload_build_id=2 \
      --upload_release_name='blue' \
      http://localhost:5000/static/dummy_page1.html
