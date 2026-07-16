"""describe_database_url must name the target and never leak the credential.

It runs inside every store factory at import time, so it must also never raise:
a helper that explodes on an odd URL would take the app down to log a line.
"""

from dashboard.backend.db_url import describe_database_url


def test_describes_host_port_and_dbname():
    described = describe_database_url(
        "postgresql://u:pw@ep-x-pooler.eu-central-1.aws.neon.tech:5432/atl?sslmode=require"
    )
    assert described == "ep-x-pooler.eu-central-1.aws.neon.tech:5432/atl"


def test_omits_port_when_the_url_has_none():
    assert describe_database_url("postgresql://fake/db") == "fake/db"


def test_never_leaks_the_password():
    described = describe_database_url("postgresql://admin:sup3r-s3cret@host/db")
    assert described == "host/db"
    assert "sup3r-s3cret" not in described


def test_keyword_dsn_degrades_without_echoing_its_input():
    # psycopg also accepts keyword/DSN strings, which urlsplit cannot read: it
    # dumps the whole string into .path. Echoing that back would put the
    # password straight into the log -- so unparseable input returns a constant.
    dsn = "host=ep-x.neon.tech dbname=atl password=sup3r-s3cret"
    described = describe_database_url(dsn)
    assert described == "?/?"
    assert "sup3r-s3cret" not in described


def test_empty_and_junk_inputs_do_not_raise():
    assert describe_database_url("") == "?/?"
    assert describe_database_url("postgresql://host:notaport/db") == "?/?"


def test_brackets_ipv6_hosts_so_host_and_port_stay_readable():
    # urlsplit strips the brackets from an IPv6 literal, and IPv6 addresses
    # are themselves colon-delimited -- so an unbracketed "::1:5432" cannot
    # be read by eye as host-vs-port, which defeats the only reason this
    # helper names the target at all.
    assert describe_database_url("postgresql://u:pw@[::1]:5432/db") == "[::1]:5432/db"


def test_reports_port_zero_rather_than_dropping_it():
    # A falsy check treats port 0 as "no port" and prints "host/db", which
    # reads identically to a URL that genuinely has no port.
    assert describe_database_url("postgresql://u:pw@host:0/db") == "host:0/db"
